import asyncio
import logging
from urllib.parse import parse_qsl, urlencode

import httpx2
import websockets
from fastapi import HTTPException, Request, Response, WebSocket, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

from gateway.config import Settings
from gateway.identity import IDENTITY_HEADERS
from gateway.routing import Route

logger = logging.getLogger(__name__)

HOP_BY_HOP_HEADERS = frozenset(
    {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"}
)
# host and content-length are recomputed by the client for the upstream request.
DROPPED_REQUEST_HEADERS = HOP_BY_HOP_HEADERS | IDENTITY_HEADERS | {"host", "content-length"}


def upstream_path(scope: dict) -> str:
    """The raw (still percent-encoded) path, so encoded characters reach the service unchanged."""
    return scope.get("raw_path", scope["path"].encode()).decode("latin-1")


def request_headers(request: Request, route: Route, identity: dict[str, str]) -> list[tuple[str, str]]:
    dropped = DROPPED_REQUEST_HEADERS if route.passes_token else DROPPED_REQUEST_HEADERS | {"authorization"}
    headers = [(name, value) for name, value in request.headers.items() if name not in dropped]
    client_host = request.client.host if request.client else ""
    forwarded_for = ", ".join(filter(None, [request.headers.get("x-forwarded-for"), client_host]))
    headers = [(name, value) for name, value in headers if not name.startswith("x-forwarded-")]
    headers += [
        ("x-forwarded-for", forwarded_for),
        ("x-forwarded-proto", request.url.scheme),
        ("x-forwarded-host", request.headers.get("host", "")),
    ]
    return headers + list(identity.items())


async def read_body(request: Request, limit: int) -> bytes:
    too_large = HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Request body is too large")
    content_length = request.headers.get("content-length")
    if content_length is not None and content_length.isdigit() and int(content_length) > limit:
        raise too_large
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise too_large
    return bytes(body)


async def forward_http(
    request: Request, client: httpx2.AsyncClient, route: Route, identity: dict[str, str], settings: Settings
) -> Response:
    url = route.upstream + upstream_path(request.scope)
    if request.url.query:
        url += "?" + request.url.query
    upstream_request = client.build_request(
        request.method,
        url,
        headers=request_headers(request, route, identity),
        content=await read_body(request, settings.max_body_size_bytes),
    )
    try:
        upstream_response = await client.send(upstream_request, stream=True)
    except httpx2.TimeoutException:
        logger.warning("Upstream %s timed out", route.upstream)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Upstream timed out") from None
    except httpx2.RequestError:
        logger.warning("Upstream %s is unavailable", route.upstream, exc_info=True)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Upstream is unavailable") from None

    response = StreamingResponse(
        upstream_response.aiter_raw(),
        status_code=upstream_response.status_code,
        background=BackgroundTask(upstream_response.aclose),
    )
    # Raw bytes are streamed as is, so content-length/encoding stay valid; repeated headers (set-cookie) are kept.
    response.raw_headers = [
        (name.encode("latin-1"), value.encode("latin-1"))
        for name, value in upstream_response.headers.multi_items()
        if name.lower() not in HOP_BY_HOP_HEADERS
    ]
    return response


async def forward_websocket(websocket: WebSocket, route: Route, identity: dict[str, str]) -> None:
    query = urlencode([(k, v) for k, v in parse_qsl(websocket.url.query, keep_blank_values=True) if k != "token"])
    url = route.upstream.replace("http", "ws", 1) + upstream_path(websocket.scope) + (f"?{query}" if query else "")
    try:
        upstream = await websockets.connect(url, additional_headers=identity, open_timeout=10)
    except InvalidStatus as exc:
        rejected = exc.response.status_code in (401, 403)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION if rejected else status.WS_1011_INTERNAL_ERROR)
        return
    except (OSError, TimeoutError, InvalidHandshake):
        logger.warning("WebSocket upstream %s is unavailable", route.upstream, exc_info=True)
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    await websocket.accept()
    async with upstream:

        async def client_to_upstream() -> None:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if message.get("text") is not None:
                    await upstream.send(message["text"])
                elif message.get("bytes") is not None:
                    await upstream.send(message["bytes"])

        async def upstream_to_client() -> None:
            try:
                async for message in upstream:
                    if isinstance(message, str):
                        await websocket.send_text(message)
                    else:
                        await websocket.send_bytes(message)
            except ConnectionClosed:
                pass
            await websocket.close(code=upstream.close_code or status.WS_1000_NORMAL_CLOSURE)

        tasks = [asyncio.create_task(client_to_upstream()), asyncio.create_task(upstream_to_client())]
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

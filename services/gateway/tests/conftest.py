import socket
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field

import httpx2
import pytest
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from gateway import main
from gateway.config import Settings, get_settings
from gateway.main import create_app

TOKENS = {
    "hero-token": ("11111111-1111-1111-1111-111111111111", "hero"),
    "corp-token": ("22222222-2222-2222-2222-222222222222", "corporation"),
}


@dataclass
class Upstreams:
    """Fake auth and services behind the gateway; records what reached the services."""

    requests: list[httpx2.Request] = field(default_factory=list)
    errors: dict[str, Exception] = field(default_factory=dict)
    auth_down: bool = False

    async def handle(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/auth/verify":
            if self.auth_down:
                raise httpx2.ConnectError("auth is down", request=request)
            token = request.headers.get("authorization", "").removeprefix("Bearer ")
            if token not in TOKENS:
                return httpx2.Response(401, json={"detail": "Invalid or expired token"})
            client_id, role = TOKENS[token]
            return httpx2.Response(200, headers={"X-Client-Id": client_id, "X-Client-Role": role})
        if request.url.path in self.errors:
            raise self.errors[request.url.path]
        self.requests.append(request)

        async def body() -> AsyncIterator[bytes]:
            yield b"upstream "
            yield b"body"

        # A streamed body: httpx2.Response pre-reads plain bytes, which a real network response never does.
        return httpx2.Response(
            201,
            headers=[("x-upstream", request.url.host), ("set-cookie", "a=1"), ("set-cookie", "b=2")],
            content=body(),
        )

    @property
    def last(self) -> httpx2.Request:
        return self.requests[-1]


@pytest.fixture
def upstreams(monkeypatch: pytest.MonkeyPatch) -> Upstreams:
    upstreams = Upstreams()

    def create_http_client(settings: Settings) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(upstreams.handle))

    monkeypatch.setattr(main, "create_http_client", create_http_client)
    return upstreams


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    def apply(**env: str) -> None:
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        get_settings.cache_clear()

    yield apply
    get_settings.cache_clear()


@pytest.fixture
def client(upstreams: Upstreams, settings_env: Callable[..., None]) -> Iterator[TestClient]:
    settings_env(MAX_BODY_SIZE_BYTES="1024")
    with TestClient(create_app()) as client:
        yield client


def ws_upstream_app() -> FastAPI:
    """Stands in for notifications: requires the identity headers and echoes back what it received."""
    app = FastAPI()

    @app.websocket("/v1/notifications/ws")
    async def ws(websocket: WebSocket) -> None:
        if "x-client-id" not in websocket.headers:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        await websocket.send_json(
            {
                "x-client-id": websocket.headers["x-client-id"],
                "x-client-role": websocket.headers["x-client-role"],
                "authorization": websocket.headers.get("authorization"),
                "query": websocket.url.query,
            }
        )
        async for text in websocket.iter_text():
            if text == "bye":
                await websocket.close(code=4000)
                return
            await websocket.send_text(f"echo: {text}")

    return app


@pytest.fixture(scope="session")
def ws_upstream_url() -> Iterator[str]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(ws_upstream_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def ws_client(upstreams: Upstreams, settings_env: Callable[..., None], ws_upstream_url: str) -> Iterator[TestClient]:
    settings_env(NOTIFICATIONS_URL=ws_upstream_url)
    with TestClient(create_app()) as client:
        yield client

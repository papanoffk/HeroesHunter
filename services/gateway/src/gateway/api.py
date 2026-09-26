from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, status

from gateway.dependencies import HttpClientDep, RoutesDep, SettingsDep
from gateway.identity import AuthUnavailableError, InvalidTokenError, extract_token, verify_token
from gateway.proxy import forward_http, forward_websocket
from gateway.routing import match_route

router = APIRouter()

PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


@router.api_route("/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
async def proxy_http(request: Request, routes: RoutesDep, client: HttpClientDep, settings: SettingsDep) -> Response:
    route = match_route(routes, request.url.path)
    if route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    identity: dict[str, str] = {}
    if not route.passes_token:
        try:
            token = extract_token(request.headers.get("authorization"))
            # No token means an anonymous request: the service itself decides whether the endpoint is public.
            if token is not None:
                identity = await verify_token(client, settings, token)
        except InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None
        except AuthUnavailableError:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Auth is unavailable") from None
    return await forward_http(request, client, route, identity, settings)


@router.websocket("/{path:path}")
async def proxy_websocket(websocket: WebSocket, routes: RoutesDep, client: HttpClientDep, settings: SettingsDep) -> None:
    route = match_route(routes, websocket.url.path)
    if route is None or route.passes_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        token = extract_token(websocket.headers.get("authorization"), websocket.query_params.get("token"))
        identity = await verify_token(client, settings, token) if token is not None else {}
    except InvalidTokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    except AuthUnavailableError:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return
    await forward_websocket(websocket, route, identity)

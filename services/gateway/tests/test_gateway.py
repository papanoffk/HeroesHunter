import httpx2
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from conftest import TOKENS, Upstreams
from gateway.routing import Route, match_route

HERO_ID, HERO_ROLE = TOKENS["hero-token"]
SPOOFED = {"X-Client-Id": "33333333-3333-3333-3333-333333333333", "X-Client-Role": "corporation"}


@pytest.mark.parametrize(
    ("path", "prefix"),
    [
        ("/v1/heroes", "/v1/heroes"),
        ("/v1/heroes/powers/1", "/v1/heroes"),
        ("/v1/heroesX", None),
        ("/auth/login", "/auth"),
        ("/authx", None),
        ("/unknown", None),
    ],
)
def test_match_route(path: str, prefix: str | None) -> None:
    routes = [Route("/auth", "http://auth"), Route("/v1/heroes", "http://heroes")]

    route = match_route(routes, path)

    assert (route.prefix if route else None) == prefix


@pytest.mark.parametrize(
    ("path", "host"),
    [
        ("/auth/login", "localhost:8000"),
        ("/v1/heroes/powers", "localhost:8001"),
        ("/v1/corporations/x", "localhost:8002"),
        ("/v1/missions", "localhost:8003"),
        ("/v1/resumes", "localhost:8004"),
    ],
)
def test_requests_are_routed_to_services(client: TestClient, upstreams: Upstreams, path: str, host: str) -> None:
    client.get(path)

    assert f"{upstreams.last.url.host}:{upstreams.last.url.port}" == host
    assert upstreams.last.url.path == path


def test_unknown_path_returns_404(client: TestClient, upstreams: Upstreams) -> None:
    assert client.get("/v1/unknown").status_code == 404
    assert upstreams.requests == []


def test_response_is_passed_through(client: TestClient) -> None:
    response = client.get("/v1/missions")

    assert response.status_code == 201
    assert response.content == b"upstream body"
    assert response.headers["x-upstream"] == "localhost"
    assert response.headers.get_list("set-cookie") == ["a=1", "b=2"]


def test_method_query_and_body_are_forwarded(client: TestClient, upstreams: Upstreams) -> None:
    client.patch("/v1/missions/abc?min_offer=5&powers_ids=1&powers_ids=2", json={"title": "X"})

    assert upstreams.last.method == "PATCH"
    assert upstreams.last.url.query == b"min_offer=5&powers_ids=1&powers_ids=2"
    assert upstreams.last.content == b'{"title":"X"}'
    assert upstreams.last.headers["content-type"] == "application/json"


def test_anonymous_request_is_forwarded_without_identity(client: TestClient, upstreams: Upstreams) -> None:
    client.get("/v1/missions", headers=SPOOFED)

    assert "x-client-id" not in upstreams.last.headers
    assert "x-client-role" not in upstreams.last.headers


def test_valid_token_is_replaced_with_identity_headers(client: TestClient, upstreams: Upstreams) -> None:
    client.post("/v1/missions", headers={"Authorization": "Bearer hero-token", **SPOOFED})

    assert upstreams.last.headers["x-client-id"] == HERO_ID
    assert upstreams.last.headers["x-client-role"] == HERO_ROLE
    assert "authorization" not in upstreams.last.headers


@pytest.mark.parametrize("authorization", ["Bearer wrong-token", "Basic abc", "Bearer ", "hero-token"])
def test_invalid_token_is_rejected_before_the_service(
    client: TestClient, upstreams: Upstreams, authorization: str
) -> None:
    response = client.get("/v1/missions", headers={"Authorization": authorization})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert upstreams.requests == []


def test_auth_routes_get_the_token_and_no_identity(client: TestClient, upstreams: Upstreams) -> None:
    client.get("/auth/me", headers={"Authorization": "Bearer anything", **SPOOFED})

    assert upstreams.last.headers["authorization"] == "Bearer anything"
    assert "x-client-id" not in upstreams.last.headers


def test_forwarded_headers_are_set(client: TestClient, upstreams: Upstreams) -> None:
    client.get("/v1/missions", headers={"X-Forwarded-For": "1.2.3.4"})

    assert upstreams.last.headers["x-forwarded-for"] == "1.2.3.4, testclient"
    assert upstreams.last.headers["x-forwarded-proto"] == "http"
    assert upstreams.last.headers["x-forwarded-host"] == "testserver"


def test_too_large_body_returns_413(client: TestClient, upstreams: Upstreams) -> None:
    assert client.post("/v1/heroes", content=b"x" * 2048).status_code == 413
    assert upstreams.requests == []


def test_upstream_errors(client: TestClient, upstreams: Upstreams) -> None:
    upstreams.errors["/v1/missions/down"] = httpx2.ConnectError("refused")
    upstreams.errors["/v1/missions/slow"] = httpx2.ReadTimeout("timeout")

    assert client.get("/v1/missions/down").status_code == 502
    assert client.get("/v1/missions/slow").status_code == 504


def test_auth_unavailable_returns_502(client: TestClient, upstreams: Upstreams) -> None:
    upstreams.auth_down = True

    assert client.get("/v1/missions", headers={"Authorization": "Bearer hero-token"}).status_code == 502
    assert upstreams.requests == []


def test_health_is_not_proxied(client: TestClient, upstreams: Upstreams) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert upstreams.requests == []


WS_PATH = "/v1/notifications/ws"


@pytest.mark.parametrize(
    ("url", "headers"),
    [
        (f"{WS_PATH}?token=hero-token&lang=en", {}),
        (f"{WS_PATH}?lang=en", {"Authorization": "Bearer hero-token"}),
    ],
)
def test_websocket_is_proxied_with_identity(ws_client: TestClient, url: str, headers: dict[str, str]) -> None:
    with ws_client.websocket_connect(url, headers={**headers, **SPOOFED}) as ws:
        received = ws.receive_json()
        ws.send_text("ping")
        echo = ws.receive_text()

    assert received == {"x-client-id": HERO_ID, "x-client-role": HERO_ROLE, "authorization": None, "query": "lang=en"}
    assert echo == "echo: ping"


def test_websocket_close_code_from_upstream_is_forwarded(ws_client: TestClient) -> None:
    with ws_client.websocket_connect(f"{WS_PATH}?token=hero-token") as ws:
        ws.receive_json()
        ws.send_text("bye")
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_text()

    assert exc_info.value.code == 4000


@pytest.mark.parametrize(
    "url",
    [f"{WS_PATH}?token=wrong-token", WS_PATH, "/v1/unknown/ws", "/auth/ws"],
)
def test_websocket_is_rejected(ws_client: TestClient, url: str) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(url):
            pass

    assert exc_info.value.code == 1008

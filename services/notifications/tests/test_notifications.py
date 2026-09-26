import time
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from notifications.schemas import Role

WS_URL = "/v1/notifications/ws"

Publish = Callable[[dict[str, Any] | bytes], None]
HeadersFactory = Callable[[UUID, Role], dict[str, str]]


def mission_responded(recipient: UUID) -> dict[str, Any]:
    return {
        "event": "mission.responded",
        "occurred_at": "2026-09-26T10:00:00+00:00",
        "recipient_uuid": str(recipient),
        "mission_uuid": str(uuid4()),
        "hero_uuid": str(uuid4()),
    }


def test_event_is_delivered_to_connected_recipient(
    client: TestClient, publish: Publish, make_headers: HeadersFactory
) -> None:
    corp = uuid4()
    event = mission_responded(corp)

    with client.websocket_connect(WS_URL, headers=make_headers(corp, Role.CORPORATION)) as ws:
        publish(event)
        assert ws.receive_json() == event


def test_event_is_delivered_to_every_connection_of_recipient(
    client: TestClient, publish: Publish, make_headers: HeadersFactory
) -> None:
    hero = uuid4()
    event = {"event": "resume.invited", "recipient_uuid": str(hero), "resume_uuid": str(uuid4())}
    headers = make_headers(hero, Role.HERO)

    with client.websocket_connect(WS_URL, headers=headers) as tab1, client.websocket_connect(WS_URL, headers=headers) as tab2:
        publish(event)
        assert tab1.receive_json() == event
        assert tab2.receive_json() == event


def test_event_is_not_delivered_to_other_clients(
    client: TestClient, publish: Publish, make_headers: HeadersFactory
) -> None:
    corp, other = uuid4(), uuid4()
    own_event = mission_responded(corp)

    with client.websocket_connect(WS_URL, headers=make_headers(corp, Role.CORPORATION)) as ws:
        publish(mission_responded(other))
        publish(own_event)
        assert ws.receive_json() == own_event


def test_event_for_offline_client_is_skipped(
    client: TestClient, publish: Publish, make_headers: HeadersFactory
) -> None:
    offline, online = uuid4(), uuid4()
    manager = client.app.state.connection_manager
    online_event = mission_responded(online)

    assert client.portal.call(manager.send, offline, mission_responded(offline)) == 0
    with client.websocket_connect(WS_URL, headers=make_headers(online, Role.CORPORATION)) as ws:
        publish(mission_responded(offline))
        publish(online_event)
        assert ws.receive_json() == online_event


@pytest.mark.parametrize(
    "body",
    [b"not json", b'{"event": "mission.responded"}', b'{"event": "x", "recipient_uuid": "not-a-uuid"}'],
)
def test_malformed_event_is_skipped(
    client: TestClient, publish: Publish, make_headers: HeadersFactory, body: bytes
) -> None:
    corp = uuid4()
    event = mission_responded(corp)

    with client.websocket_connect(WS_URL, headers=make_headers(corp, Role.CORPORATION)) as ws:
        publish(body)
        publish(event)
        assert ws.receive_json() == event


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Client-Id": str(uuid4())}, {"X-Client-Id": "garbage", "X-Client-Role": "hero"}],
)
def test_connection_without_valid_identity_is_rejected(client: TestClient, headers: dict[str, str]) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(WS_URL, headers=headers):
            pass

    assert exc_info.value.code == 1008


def test_disconnected_client_is_removed(client: TestClient, make_headers: HeadersFactory) -> None:
    hero = uuid4()
    manager = client.app.state.connection_manager

    with client.websocket_connect(WS_URL, headers=make_headers(hero, Role.HERO)):
        pass

    for _ in range(50):
        if hero not in manager._connections:
            break
        time.sleep(0.01)
    assert hero not in manager._connections

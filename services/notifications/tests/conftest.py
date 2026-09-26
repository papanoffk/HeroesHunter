import json
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from notifications import main
from notifications.config import Settings
from notifications.connections import ConnectionManager
from notifications.consumer import EventConsumer
from notifications.main import create_app
from notifications.schemas import Role


@pytest.fixture
def consumer(monkeypatch: pytest.MonkeyPatch) -> list[EventConsumer]:
    """The real consumer without a broker connection; filled when the app starts."""
    created: list[EventConsumer] = []

    async def start(_: Settings, manager: ConnectionManager) -> EventConsumer:
        created.append(EventConsumer(manager))
        return created[0]

    monkeypatch.setattr(main, "start_consumer", start)
    return created


@pytest.fixture
def client(consumer: list[EventConsumer]) -> Iterator[TestClient]:
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture
def publish(client: TestClient, consumer: list[EventConsumer]) -> Callable[[dict[str, Any] | bytes], None]:
    """Feeds a message body to the consumer inside the app's event loop, as RabbitMQ would."""

    def publish(event: dict[str, Any] | bytes) -> None:
        body = event if isinstance(event, bytes) else json.dumps(event, default=str).encode()
        client.portal.call(consumer[0].handle, body)

    return publish


@pytest.fixture
def make_headers() -> Callable[[UUID, Role], dict[str, str]]:
    def make(client_id: UUID, role: Role) -> dict[str, str]:
        return {"X-Client-Id": str(client_id), "X-Client-Role": role.value}

    return make

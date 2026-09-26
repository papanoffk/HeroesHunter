from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from resumes import main, migrate
from resumes.config import Settings, get_settings
from resumes.main import create_app
from resumes.schemas import Role


@pytest.fixture(scope="session")
def settings() -> Iterator[Settings]:
    """Runs the real migrator into a throwaway schema; skips DB tests if Postgres is unavailable."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DB_SCHEMA", f"resumes_test_{uuid4().hex[:8]}")
        get_settings.cache_clear()
        settings = get_settings()
        try:
            migrate.main()
        except psycopg.OperationalError as exc:
            pytest.skip(f"Postgres is unavailable: {exc}")
        yield settings
        with psycopg.connect(settings.dsn(), autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(settings.db_schema)))
    get_settings.cache_clear()


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        self.events.append((routing_key, payload))

    async def close(self) -> None:
        pass


@pytest.fixture
def publisher(monkeypatch: pytest.MonkeyPatch) -> RecordingPublisher:
    publisher = RecordingPublisher()

    async def connect(_: Settings) -> RecordingPublisher:
        return publisher

    monkeypatch.setattr(main, "connect_publisher", connect)
    return publisher


@pytest.fixture
def client(settings: Settings, publisher: RecordingPublisher) -> Iterator[TestClient]:
    with psycopg.connect(settings.dsn(), autocommit=True) as conn:
        conn.execute(sql.SQL("TRUNCATE {}.resume").format(sql.Identifier(settings.db_schema)))
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture
def make_headers() -> Callable[[UUID, Role], dict[str, str]]:
    def make(client_id: UUID, role: Role) -> dict[str, str]:
        return {"X-Client-Id": str(client_id), "X-Client-Role": role.value}

    return make

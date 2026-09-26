from collections.abc import Callable, Iterator
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from missions import migrate
from missions.config import Settings, get_settings
from missions.main import create_app
from missions.schemas import Role


@pytest.fixture(scope="session")
def settings() -> Iterator[Settings]:
    """Runs the real migrator into a throwaway schema; skips DB tests if Postgres is unavailable."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DB_SCHEMA", f"missions_test_{uuid4().hex[:8]}")
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


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with psycopg.connect(settings.dsn(), autocommit=True) as conn:
        conn.execute(sql.SQL("TRUNCATE {}.missions").format(sql.Identifier(settings.db_schema)))
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture
def make_headers() -> Callable[[UUID, Role], dict[str, str]]:
    def make(client_id: UUID, role: Role) -> dict[str, str]:
        return {"X-Client-Id": str(client_id), "X-Client-Role": role.value}

    return make

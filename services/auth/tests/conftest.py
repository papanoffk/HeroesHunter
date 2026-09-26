from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from auth.config import Settings, get_settings
from auth.dependencies import get_client_repository
from auth.main import create_app
from auth.repository import Client, ClientAlreadyExistsError
from auth.schemas import Role


class InMemoryClientRepository:
    def __init__(self) -> None:
        self.clients: dict[UUID, Client] = {}

    async def create(self, email: str, pass_hash: str, role: Role) -> Client:
        if await self.get_by_email(email, role):
            raise ClientAlreadyExistsError
        client = Client(uuid4(), email, pass_hash, role, datetime.now(UTC))
        self.clients[client.client_uuid] = client
        return client

    async def get_by_email(self, email: str, role: Role) -> Client | None:
        return next((c for c in self.clients.values() if c.email == email and c.role == role), None)

    async def get_by_id(self, client_uuid: UUID) -> Client | None:
        return self.clients.get(client_uuid)


@pytest.fixture
def settings() -> Settings:
    return Settings(jwt_secret="test-secret-test-secret-test-secret-42")


@pytest.fixture
def repo() -> InMemoryClientRepository:
    return InMemoryClientRepository()


@pytest.fixture
def client(settings: Settings, repo: InMemoryClientRepository) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_client_repository] = lambda: repo
    # Not used as a context manager, so lifespan (DB pool) is not started.
    return TestClient(app)

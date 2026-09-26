from collections.abc import Callable
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from corporations.config import Settings, get_settings
from corporations.dependencies import get_corp_repository
from corporations.main import create_app
from corporations.repository import Corp, CorpAlreadyExistsError
from corporations.schemas import Role


class InMemoryCorpRepository:
    def __init__(self) -> None:
        self.corps: dict[UUID, tuple[str, str | None, bytes | None]] = {}

    async def create(self, client_uuid: UUID, name: str, description: str | None, image: bytes | None) -> Corp:
        if client_uuid in self.corps:
            raise CorpAlreadyExistsError
        self.corps[client_uuid] = (name, description, image)
        return Corp(client_uuid, name, description, image is not None)

    async def get(self, client_uuid: UUID) -> Corp | None:
        if client_uuid not in self.corps:
            return None
        name, description, image = self.corps[client_uuid]
        return Corp(client_uuid, name, description, image is not None)

    async def get_image(self, client_uuid: UUID) -> bytes | None:
        return self.corps.get(client_uuid, ("", None, None))[2]

    async def update(
        self, client_uuid: UUID, name: str | None, description: str | None, image: bytes | None
    ) -> Corp | None:
        if client_uuid not in self.corps:
            return None
        old_name, old_description, old_image = self.corps[client_uuid]
        self.corps[client_uuid] = (name or old_name, description or old_description, image or old_image)
        return await self.get(client_uuid)


@pytest.fixture
def settings() -> Settings:
    return Settings(max_image_size_bytes=1024)


@pytest.fixture
def make_headers() -> Callable[[UUID, Role], dict[str, str]]:
    def make(client_id: UUID, role: Role = Role.CORPORATION) -> dict[str, str]:
        return {"X-Client-Id": str(client_id), "X-Client-Role": role.value}

    return make


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app()
    repo = InMemoryCorpRepository()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_corp_repository] = lambda: repo
    return TestClient(app)

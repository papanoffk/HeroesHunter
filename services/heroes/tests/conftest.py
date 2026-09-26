from collections.abc import Callable
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from heroes.config import Settings, get_settings
from heroes.dependencies import get_hero_repository, get_power_repository
from heroes.main import create_app
from heroes.repository import Hero, HeroAlreadyExistsError, Power
from heroes.schemas import Role


class InMemoryHeroRepository:
    def __init__(self) -> None:
        self.heroes: dict[UUID, tuple[str, bytes | None]] = {}

    async def create(self, client_uuid: UUID, name: str, image: bytes | None) -> Hero:
        if client_uuid in self.heroes:
            raise HeroAlreadyExistsError
        self.heroes[client_uuid] = (name, image)
        return Hero(client_uuid, name, image is not None)

    async def get(self, client_uuid: UUID) -> Hero | None:
        if client_uuid not in self.heroes:
            return None
        name, image = self.heroes[client_uuid]
        return Hero(client_uuid, name, image is not None)

    async def get_image(self, client_uuid: UUID) -> bytes | None:
        return self.heroes.get(client_uuid, ("", None))[1]

    async def update(self, client_uuid: UUID, name: str | None, image: bytes | None) -> Hero | None:
        if client_uuid not in self.heroes:
            return None
        old_name, old_image = self.heroes[client_uuid]
        self.heroes[client_uuid] = (name or old_name, image or old_image)
        return await self.get(client_uuid)


class InMemoryPowerRepository:
    powers = [Power(1, "Super Strength"), Power(2, "Flight")]

    async def list(self) -> list[Power]:
        return self.powers

    async def get(self, power_id: int) -> Power | None:
        return next((p for p in self.powers if p.power_id == power_id), None)


@pytest.fixture
def settings() -> Settings:
    return Settings(max_image_size_bytes=1024)


@pytest.fixture
def make_headers() -> Callable[[UUID, Role], dict[str, str]]:
    def make(client_id: UUID, role: Role = Role.HERO) -> dict[str, str]:
        return {"X-Client-Id": str(client_id), "X-Client-Role": role.value}

    return make


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app()
    hero_repo = InMemoryHeroRepository()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_hero_repository] = lambda: hero_repo
    app.dependency_overrides[get_power_repository] = InMemoryPowerRepository
    return TestClient(app)

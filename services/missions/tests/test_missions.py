import asyncio
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

from missions.config import Settings
from missions.db import create_pool
from missions.events import MISSION_RESPONDED, EventPublisher
from missions.repository import AlreadyRespondedError, MissionRepository
from missions.schemas import Role
from conftest import RecordingPublisher

HeadersFactory = Callable[[UUID, Role], dict[str, str]]

MISSION = {
    "title": "Save the city",
    "descriptions": "Giant robot attack",
    "location": "Metropolis",
    "powers_ids": [1, 2],
    "work_experience": 3,
    "offer": 1000,
}


@pytest.fixture
def corp() -> UUID:
    return uuid4()


@pytest.fixture
def corp_headers(corp: UUID, make_headers: HeadersFactory) -> dict[str, str]:
    return make_headers(corp, Role.CORPORATION)


def create_mission(client: TestClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    response = client.post("/v1/missions", json=MISSION | overrides, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def respond(client: TestClient, mission: dict[str, Any], hero: UUID, make_headers: HeadersFactory) -> int:
    url = f"/v1/missions/{mission['missions_uuid']}/respond"
    return client.post(url, headers=make_headers(hero, Role.HERO)).status_code


def test_create_mission(client: TestClient, corp: UUID, corp_headers: dict[str, str]) -> None:
    mission = create_mission(client, corp_headers)

    assert mission == {
        "missions_uuid": mission["missions_uuid"],
        "owner_uuid": str(corp),
        **MISSION,
        "created_at": mission["created_at"],
        "respondents_uuids": [],
        "new_respondents_uuids": [],
    }


def test_create_mission_defaults(client: TestClient, corp_headers: dict[str, str]) -> None:
    response = client.post("/v1/missions", json={"title": "Minimal"}, headers=corp_headers)

    assert response.status_code == 201
    assert response.json()["powers_ids"] == []
    assert response.json()["work_experience"] == 0
    assert response.json()["offer"] is None


def test_create_mission_access_and_validation(
    client: TestClient, corp_headers: dict[str, str], make_headers: HeadersFactory
) -> None:
    assert client.post("/v1/missions", json=MISSION, headers=make_headers(uuid4(), Role.HERO)).status_code == 403
    assert client.post("/v1/missions", json=MISSION).status_code == 401
    for bad in ({"owner_uuid": str(uuid4())}, {"title": ""}, {"title": "x" * 201}, {"offer": -1}, {"work_experience": -1}, {"powers_ids": [0]}):
        assert client.post("/v1/missions", json=MISSION | bad, headers=corp_headers).status_code == 422, bad


def test_respondents_visible_only_to_owner(
    client: TestClient, corp_headers: dict[str, str], make_headers: HeadersFactory
) -> None:
    mission = create_mission(client, corp_headers)
    url = f"/v1/missions/{mission['missions_uuid']}"

    anonymous = client.get(url).json()
    other_corp = client.get(url, headers=make_headers(uuid4(), Role.CORPORATION)).json()
    owner = client.get(url, headers=corp_headers).json()

    assert anonymous["title"] == MISSION["title"]
    assert anonymous["respondents_uuids"] is None and anonymous["new_respondents_uuids"] is None
    assert other_corp["new_respondents_uuids"] is None
    assert owner["new_respondents_uuids"] == []
    assert client.get("/v1/missions").json()[0]["new_respondents_uuids"] is None
    assert client.get("/v1/missions", headers=corp_headers).json()[0]["new_respondents_uuids"] == []


def test_get_mission_errors(client: TestClient) -> None:
    assert client.get(f"/v1/missions/{uuid4()}").status_code == 404
    assert client.get(f"/v1/missions/{uuid4()}", headers={"X-Client-Id": "garbage"}).status_code == 401


def test_list_filters(client: TestClient, corp_headers: dict[str, str]) -> None:
    cheap = create_mission(client, corp_headers, title="cheap", offer=100, work_experience=0, powers_ids=[1])
    mid = create_mission(client, corp_headers, title="mid", offer=500, work_experience=2, powers_ids=[2, 3])
    rich = create_mission(client, corp_headers, title="rich", offer=1000, work_experience=5, powers_ids=[4])
    create_mission(client, corp_headers, title="no offer", offer=None, work_experience=0, powers_ids=[])

    def titles(**params: Any) -> set[str]:
        response = client.get("/v1/missions", params=params)
        assert response.status_code == 200, response.text
        return {mission["title"] for mission in response.json()}

    assert titles() == {"cheap", "mid", "rich", "no offer"}
    assert [m["title"] for m in client.get("/v1/missions").json()] == ["no offer", "rich", "mid", "cheap"]
    assert titles(min_offer=500) == {mid["title"], rich["title"]}
    assert titles(max_offer=500) == {cheap["title"], mid["title"]}
    assert titles(max_work_experience=2) == {"cheap", "mid", "no offer"}
    assert titles(powers_ids=[1, 3]) == {"cheap", "mid"}
    assert titles(min_offer=200, max_work_experience=2, powers_ids=[2]) == {"mid"}
    assert len(client.get("/v1/missions", params={"limit": 3}).json()) == 3
    assert len(client.get("/v1/missions", params={"limit": 3, "offset": 3}).json()) == 1
    assert client.get("/v1/missions", params={"limit": 101}).status_code == 422


def test_update_mission(client: TestClient, corp_headers: dict[str, str]) -> None:
    mission = create_mission(client, corp_headers)
    url = f"/v1/missions/{mission['missions_uuid']}"

    response = client.patch(url, json={"title": "New title", "offer": None, "powers_ids": [5]}, headers=corp_headers)

    assert response.status_code == 200
    assert response.json() == mission | {"title": "New title", "offer": None, "powers_ids": [5]}


def test_update_mission_validation_and_access(
    client: TestClient, corp_headers: dict[str, str], make_headers: HeadersFactory
) -> None:
    url = f"/v1/missions/{create_mission(client, corp_headers)['missions_uuid']}"

    assert client.patch(url, json={}, headers=corp_headers).status_code == 422
    assert client.patch(url, json={"title": None}, headers=corp_headers).status_code == 422
    assert client.patch(url, json={"title": "X", "respondents_uuids": []}, headers=corp_headers).status_code == 422
    assert client.patch(url, json={"created_at": "2000-01-01T00:00:00Z"}, headers=corp_headers).status_code == 422
    assert client.patch(url, json={"title": "X"}, headers=make_headers(uuid4(), Role.CORPORATION)).status_code == 403
    assert client.patch(f"/v1/missions/{uuid4()}", json={"title": "X"}, headers=corp_headers).status_code == 404


def test_delete_mission(client: TestClient, corp_headers: dict[str, str], make_headers: HeadersFactory) -> None:
    url = f"/v1/missions/{create_mission(client, corp_headers)['missions_uuid']}"

    assert client.delete(url, headers=make_headers(uuid4(), Role.CORPORATION)).status_code == 403
    assert client.delete(url, headers=corp_headers).status_code == 204
    assert client.get(url).status_code == 404
    assert client.delete(url, headers=corp_headers).status_code == 404


def test_respond_flow(client: TestClient, corp_headers: dict[str, str], make_headers: HeadersFactory) -> None:
    mission = create_mission(client, corp_headers)
    url = f"/v1/missions/{mission['missions_uuid']}"
    hero_a, hero_b, hero_c = uuid4(), uuid4(), uuid4()

    for hero in (hero_a, hero_b, hero_c):
        assert respond(client, mission, hero, make_headers) == 204
    assert respond(client, mission, hero_a, make_headers) == 409

    owner_view = client.get(url, headers=corp_headers).json()
    assert owner_view["new_respondents_uuids"] == [str(hero_a), str(hero_b), str(hero_c)]
    assert owner_view["respondents_uuids"] == []

    viewed = client.post(
        f"{url}/view", json={"respondents_uuids": [str(hero_c), str(hero_a), str(uuid4())]}, headers=corp_headers
    )
    assert viewed.status_code == 200
    assert viewed.json()["respondents_uuids"] == [str(hero_a), str(hero_c)]
    assert viewed.json()["new_respondents_uuids"] == [str(hero_b)]

    again = client.post(f"{url}/view", json={"respondents_uuids": [str(hero_a)]}, headers=corp_headers)
    assert again.json()["respondents_uuids"] == [str(hero_a), str(hero_c)]
    assert respond(client, mission, hero_a, make_headers) == 409


def test_respond_access(client: TestClient, corp_headers: dict[str, str], make_headers: HeadersFactory) -> None:
    mission = create_mission(client, corp_headers)
    url = f"/v1/missions/{mission['missions_uuid']}/respond"

    assert client.post(url, headers=corp_headers).status_code == 403
    assert client.post(url).status_code == 401
    assert client.post(f"/v1/missions/{uuid4()}/respond", headers=make_headers(uuid4(), Role.HERO)).status_code == 404


def test_view_access_and_validation(
    client: TestClient, corp_headers: dict[str, str], make_headers: HeadersFactory
) -> None:
    url = f"/v1/missions/{create_mission(client, corp_headers)['missions_uuid']}/view"
    body = {"respondents_uuids": [str(uuid4())]}

    assert client.post(url, json={"respondents_uuids": []}, headers=corp_headers).status_code == 422
    assert client.post(url, json=body, headers=make_headers(uuid4(), Role.CORPORATION)).status_code == 403
    assert client.post(url, json=body, headers=make_headers(uuid4(), Role.HERO)).status_code == 403
    assert client.post(f"/v1/missions/{uuid4()}/view", json=body, headers=corp_headers).status_code == 404


def test_concurrent_responses_do_not_duplicate_hero(
    client: TestClient, settings: Settings, corp_headers: dict[str, str]
) -> None:
    mission_uuid = UUID(create_mission(client, corp_headers)["missions_uuid"])
    hero = uuid4()

    async def respond_once(pool: asyncpg.Pool) -> str:
        async with pool.acquire() as conn:
            try:
                await MissionRepository(conn).respond(mission_uuid, hero)
                return "ok"
            except AlreadyRespondedError:
                return "duplicate"

    async def run() -> list[str]:
        pool = await create_pool(settings)
        try:
            return await asyncio.gather(*(respond_once(pool) for _ in range(5)))
        finally:
            await pool.close()

    assert sorted(asyncio.run(run())) == ["duplicate"] * 4 + ["ok"]
    assert client.get(f"/v1/missions/{mission_uuid}", headers=corp_headers).json()["new_respondents_uuids"] == [
        str(hero)
    ]


def test_respond_publishes_event_for_mission_owner(
    client: TestClient,
    corp: UUID,
    corp_headers: dict[str, str],
    make_headers: HeadersFactory,
    publisher: RecordingPublisher,
) -> None:
    mission = create_mission(client, corp_headers)
    hero = uuid4()

    assert respond(client, mission, hero, make_headers) == 204
    assert respond(client, mission, hero, make_headers) == 409

    assert publisher.events == [
        (
            MISSION_RESPONDED,
            {"recipient_uuid": corp, "mission_uuid": UUID(mission["missions_uuid"]), "hero_uuid": hero},
        )
    ]


def test_publisher_failure_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    class BrokenExchange:
        async def publish(self, *args: Any, **kwargs: Any) -> None:
            raise ConnectionError("broker is down")

    publisher = EventPublisher(connection=None, exchange=BrokenExchange(), timeout=1)  # type: ignore[arg-type]

    asyncio.run(publisher.publish(MISSION_RESPONDED, {"recipient_uuid": uuid4()}))

    assert "Failed to publish mission.responded event" in caplog.text

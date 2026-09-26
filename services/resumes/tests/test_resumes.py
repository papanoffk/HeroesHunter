import asyncio
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

from resumes.config import Settings
from resumes.db import create_pool
from resumes.repository import AlreadyInvitedError, ResumeRepository
from resumes.schemas import Role

HeadersFactory = Callable[[UUID, Role], dict[str, str]]

RESUME = {
    "title": "Superhero",
    "descriptions": "Fast and strong",
    "previous_works": "Justice League (5 years), Wayne Enterprises",
    "powers_ids": [1, 2],
    "work_experience": 5,
    "offer": 1000,
}


@pytest.fixture
def hero() -> UUID:
    return uuid4()


@pytest.fixture
def hero_headers(hero: UUID, make_headers: HeadersFactory) -> dict[str, str]:
    return make_headers(hero, Role.HERO)


def create_resume(client: TestClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    response = client.post("/v1/resumes", json=RESUME | overrides, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def invite(client: TestClient, resume: dict[str, Any], corp: UUID, make_headers: HeadersFactory) -> int:
    url = f"/v1/resumes/{resume['resume_uuid']}/invitation"
    return client.post(url, headers=make_headers(corp, Role.CORPORATION)).status_code


def test_create_resume(client: TestClient, hero: UUID, hero_headers: dict[str, str]) -> None:
    resume = create_resume(client, hero_headers)

    assert resume == {
        "resume_uuid": resume["resume_uuid"],
        "owner_uuid": str(hero),
        **RESUME,
        "created_at": resume["created_at"],
        "invitations_corp_uuids": [],
        "new_invitations_corp_uuids": [],
    }


def test_create_resume_defaults(client: TestClient, hero_headers: dict[str, str]) -> None:
    response = client.post("/v1/resumes", json={"title": "Minimal"}, headers=hero_headers)

    assert response.status_code == 201
    assert response.json()["previous_works"] is None
    assert response.json()["powers_ids"] == []
    assert response.json()["work_experience"] == 0
    assert response.json()["offer"] is None


def test_create_resume_access_and_validation(
    client: TestClient, hero_headers: dict[str, str], make_headers: HeadersFactory
) -> None:
    assert client.post("/v1/resumes", json=RESUME, headers=make_headers(uuid4(), Role.CORPORATION)).status_code == 403
    assert client.post("/v1/resumes", json=RESUME).status_code == 401
    for bad in (
        {"owner_uuid": str(uuid4())},
        {"title": ""},
        {"title": "x" * 201},
        {"offer": -1},
        {"work_experience": -1},
        {"powers_ids": [0]},
        {"previous_works": ["not", "text"]},
    ):
        assert client.post("/v1/resumes", json=RESUME | bad, headers=hero_headers).status_code == 422, bad


def test_invitations_visible_only_to_owner(
    client: TestClient, hero_headers: dict[str, str], make_headers: HeadersFactory
) -> None:
    resume = create_resume(client, hero_headers)
    url = f"/v1/resumes/{resume['resume_uuid']}"

    anonymous = client.get(url).json()
    corp = client.get(url, headers=make_headers(uuid4(), Role.CORPORATION)).json()
    owner = client.get(url, headers=hero_headers).json()

    assert anonymous["title"] == RESUME["title"]
    assert anonymous["invitations_corp_uuids"] is None and anonymous["new_invitations_corp_uuids"] is None
    assert corp["new_invitations_corp_uuids"] is None
    assert owner["new_invitations_corp_uuids"] == []
    assert client.get("/v1/resumes").json()[0]["new_invitations_corp_uuids"] is None
    assert client.get("/v1/resumes", headers=hero_headers).json()[0]["new_invitations_corp_uuids"] == []


def test_get_resume_errors(client: TestClient) -> None:
    assert client.get(f"/v1/resumes/{uuid4()}").status_code == 404
    assert client.get(f"/v1/resumes/{uuid4()}", headers={"X-Client-Id": "garbage"}).status_code == 401


def test_list_filters_and_order(client: TestClient, hero_headers: dict[str, str]) -> None:
    create_resume(client, hero_headers, title="junior", offer=100, work_experience=0, powers_ids=[1])
    create_resume(client, hero_headers, title="middle", offer=500, work_experience=3, powers_ids=[2, 3])
    create_resume(client, hero_headers, title="senior", offer=1000, work_experience=10, powers_ids=[4])
    create_resume(client, hero_headers, title="no offer", offer=None, work_experience=1, powers_ids=[])

    def titles(**params: Any) -> set[str]:
        response = client.get("/v1/resumes", params=params)
        assert response.status_code == 200, response.text
        return {resume["title"] for resume in response.json()}

    assert [r["title"] for r in client.get("/v1/resumes").json()] == ["no offer", "senior", "middle", "junior"]
    assert titles(min_offer=500) == {"middle", "senior"}
    assert titles(max_offer=500) == {"junior", "middle"}
    assert titles(min_work_experience=3) == {"middle", "senior"}
    assert titles(powers_ids=[1, 3]) == {"junior", "middle"}
    assert titles(max_offer=800, min_work_experience=1, powers_ids=[3]) == {"middle"}
    assert len(client.get("/v1/resumes", params={"limit": 3}).json()) == 3
    assert len(client.get("/v1/resumes", params={"limit": 3, "offset": 3}).json()) == 1
    assert client.get("/v1/resumes", params={"limit": 101}).status_code == 422


def test_update_resume(client: TestClient, hero_headers: dict[str, str]) -> None:
    resume = create_resume(client, hero_headers)
    url = f"/v1/resumes/{resume['resume_uuid']}"
    changes = {"title": "Team lead", "previous_works": None, "offer": None, "powers_ids": [5]}

    response = client.patch(url, json=changes, headers=hero_headers)

    assert response.status_code == 200
    assert response.json() == resume | changes


def test_update_resume_validation_and_access(
    client: TestClient, hero_headers: dict[str, str], make_headers: HeadersFactory
) -> None:
    url = f"/v1/resumes/{create_resume(client, hero_headers)['resume_uuid']}"

    assert client.patch(url, json={}, headers=hero_headers).status_code == 422
    assert client.patch(url, json={"title": None}, headers=hero_headers).status_code == 422
    assert client.patch(url, json={"title": "X", "invitations_corp_uuids": []}, headers=hero_headers).status_code == 422
    assert client.patch(url, json={"created_at": "2000-01-01T00:00:00Z"}, headers=hero_headers).status_code == 422
    assert client.patch(url, json={"title": "X"}, headers=make_headers(uuid4(), Role.HERO)).status_code == 403
    assert client.patch(f"/v1/resumes/{uuid4()}", json={"title": "X"}, headers=hero_headers).status_code == 404


def test_delete_resume(client: TestClient, hero_headers: dict[str, str], make_headers: HeadersFactory) -> None:
    url = f"/v1/resumes/{create_resume(client, hero_headers)['resume_uuid']}"

    assert client.delete(url, headers=make_headers(uuid4(), Role.HERO)).status_code == 403
    assert client.delete(url, headers=hero_headers).status_code == 204
    assert client.get(url).status_code == 404
    assert client.delete(url, headers=hero_headers).status_code == 404


def test_invitation_flow(client: TestClient, hero_headers: dict[str, str], make_headers: HeadersFactory) -> None:
    resume = create_resume(client, hero_headers)
    url = f"/v1/resumes/{resume['resume_uuid']}"
    corp_a, corp_b, corp_c = uuid4(), uuid4(), uuid4()

    for corp in (corp_a, corp_b, corp_c):
        assert invite(client, resume, corp, make_headers) == 204
    assert invite(client, resume, corp_a, make_headers) == 409

    owner_view = client.get(url, headers=hero_headers).json()
    assert owner_view["new_invitations_corp_uuids"] == [str(corp_a), str(corp_b), str(corp_c)]
    assert owner_view["invitations_corp_uuids"] == []

    viewed = client.post(
        f"{url}/view", json={"invitations_corp_uuids": [str(corp_c), str(corp_a), str(uuid4())]}, headers=hero_headers
    )
    assert viewed.status_code == 200
    assert viewed.json()["invitations_corp_uuids"] == [str(corp_a), str(corp_c)]
    assert viewed.json()["new_invitations_corp_uuids"] == [str(corp_b)]

    again = client.post(f"{url}/view", json={"invitations_corp_uuids": [str(corp_a)]}, headers=hero_headers)
    assert again.json()["invitations_corp_uuids"] == [str(corp_a), str(corp_c)]
    assert invite(client, resume, corp_a, make_headers) == 409


def test_invitation_access(client: TestClient, hero_headers: dict[str, str], make_headers: HeadersFactory) -> None:
    resume = create_resume(client, hero_headers)
    url = f"/v1/resumes/{resume['resume_uuid']}/invitation"

    assert client.post(url, headers=hero_headers).status_code == 403
    assert client.post(url).status_code == 401
    assert (
        client.post(f"/v1/resumes/{uuid4()}/invitation", headers=make_headers(uuid4(), Role.CORPORATION)).status_code
        == 404
    )


def test_view_access_and_validation(
    client: TestClient, hero_headers: dict[str, str], make_headers: HeadersFactory
) -> None:
    url = f"/v1/resumes/{create_resume(client, hero_headers)['resume_uuid']}/view"
    body = {"invitations_corp_uuids": [str(uuid4())]}

    assert client.post(url, json={"invitations_corp_uuids": []}, headers=hero_headers).status_code == 422
    assert client.post(url, json=body, headers=make_headers(uuid4(), Role.HERO)).status_code == 403
    assert client.post(url, json=body, headers=make_headers(uuid4(), Role.CORPORATION)).status_code == 403
    assert client.post(f"/v1/resumes/{uuid4()}/view", json=body, headers=hero_headers).status_code == 404


def test_concurrent_invitations_do_not_duplicate_corporation(
    client: TestClient, settings: Settings, hero_headers: dict[str, str]
) -> None:
    resume_uuid = UUID(create_resume(client, hero_headers)["resume_uuid"])
    corp = uuid4()

    async def invite_once(pool: asyncpg.Pool) -> str:
        async with pool.acquire() as conn:
            try:
                await ResumeRepository(conn).invite(resume_uuid, corp)
                return "ok"
            except AlreadyInvitedError:
                return "duplicate"

    async def run() -> list[str]:
        pool = await create_pool(settings)
        try:
            return await asyncio.gather(*(invite_once(pool) for _ in range(5)))
        finally:
            await pool.close()

    assert sorted(asyncio.run(run())) == ["duplicate"] * 4 + ["ok"]
    assert client.get(f"/v1/resumes/{resume_uuid}", headers=hero_headers).json()["new_invitations_corp_uuids"] == [
        str(corp)
    ]

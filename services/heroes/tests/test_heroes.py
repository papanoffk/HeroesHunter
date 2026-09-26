from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from heroes.schemas import Role

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff" + b"\x00" * 16

HeadersFactory = Callable[..., dict[str, str]]


def create_hero(client: TestClient, headers: dict[str, str], client_uuid: UUID, image: bytes | None = None):
    files = {"image": ("hero.png", image, "image/png")} if image else None
    return client.post(
        "/v1/heroes", data={"client_uuid": str(client_uuid), "name": "Batman"}, files=files, headers=headers
    )


@pytest.fixture
def hero_id(client: TestClient, make_headers: HeadersFactory) -> UUID:
    hero_id = uuid4()
    assert create_hero(client, make_headers(hero_id), hero_id, PNG).status_code == 201
    return hero_id


def test_list_and_get_powers(client: TestClient) -> None:
    assert client.get("/v1/heroes/powers").json() == [
        {"power_id": 1, "title": "Super Strength"},
        {"power_id": 2, "title": "Flight"},
    ]
    assert client.get("/v1/heroes/powers/2").json() == {"power_id": 2, "title": "Flight"}
    assert client.get("/v1/heroes/powers/99").status_code == 404


def test_create_hero(client: TestClient, make_headers: HeadersFactory) -> None:
    hero_id = uuid4()

    response = create_hero(client, make_headers(hero_id), hero_id, PNG)

    assert response.status_code == 201
    assert response.json() == {
        "client_uuid": str(hero_id),
        "name": "Batman",
        "image_url": f"/v1/heroes/{hero_id}/image",
    }


def test_create_hero_without_image(client: TestClient, make_headers: HeadersFactory) -> None:
    hero_id = uuid4()

    response = create_hero(client, make_headers(hero_id), hero_id)

    assert response.status_code == 201
    assert response.json()["image_url"] is None


def test_create_hero_duplicate_returns_409(client: TestClient, make_headers: HeadersFactory, hero_id: UUID) -> None:
    assert create_hero(client, make_headers(hero_id), hero_id).status_code == 409


def test_create_hero_forbidden_for_other_client_or_corporation(
    client: TestClient, make_headers: HeadersFactory
) -> None:
    hero_id = uuid4()

    assert create_hero(client, make_headers(uuid4()), hero_id).status_code == 403
    assert create_hero(client, make_headers(hero_id, Role.CORPORATION), hero_id).status_code == 403
    assert create_hero(client, {}, hero_id).status_code == 401


def test_create_hero_rejects_bad_images(client: TestClient, make_headers: HeadersFactory) -> None:
    hero_id = uuid4()
    headers = make_headers(hero_id)

    assert create_hero(client, headers, hero_id, b"not an image").status_code == 415
    assert create_hero(client, headers, hero_id, PNG + b"\x00" * 2048).status_code == 413


def test_get_hero_only_for_owner(client: TestClient, make_headers: HeadersFactory, hero_id: UUID) -> None:
    assert client.get(f"/v1/heroes/{hero_id}", headers=make_headers(hero_id)).json()["name"] == "Batman"
    assert client.get(f"/v1/heroes/{hero_id}", headers=make_headers(uuid4())).status_code == 403
    assert client.get(f"/v1/heroes/{hero_id}").status_code == 401


def test_get_missing_hero_returns_404(client: TestClient, make_headers: HeadersFactory) -> None:
    hero_id = uuid4()

    assert client.get(f"/v1/heroes/{hero_id}", headers=make_headers(hero_id)).status_code == 404


def test_get_hero_image(client: TestClient, make_headers: HeadersFactory, hero_id: UUID) -> None:
    response = client.get(f"/v1/heroes/{hero_id}/image", headers=make_headers(hero_id))

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == PNG


def test_update_hero(client: TestClient, make_headers: HeadersFactory, hero_id: UUID) -> None:
    headers = make_headers(hero_id)

    renamed = client.patch(f"/v1/heroes/{hero_id}", data={"name": "Dark Knight"}, headers=headers)
    new_image = client.patch(
        f"/v1/heroes/{hero_id}", files={"image": ("hero.jpg", JPEG, "image/jpeg")}, headers=headers
    )

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Dark Knight"
    assert new_image.status_code == 200
    assert new_image.json()["name"] == "Dark Knight"
    assert client.get(f"/v1/heroes/{hero_id}/image", headers=headers).headers["content-type"] == "image/jpeg"


def test_update_hero_validation_and_access(client: TestClient, make_headers: HeadersFactory, hero_id: UUID) -> None:
    missing = uuid4()

    assert client.patch(f"/v1/heroes/{hero_id}", headers=make_headers(hero_id)).status_code == 422
    assert client.patch(f"/v1/heroes/{hero_id}", data={"name": ""}, headers=make_headers(hero_id)).status_code == 422
    assert client.patch(f"/v1/heroes/{hero_id}", data={"name": "X"}, headers=make_headers(uuid4())).status_code == 403
    assert client.patch(f"/v1/heroes/{missing}", data={"name": "X"}, headers=make_headers(missing)).status_code == 404


def test_missing_or_invalid_gateway_headers_return_401(client: TestClient, hero_id: UUID) -> None:
    url = f"/v1/heroes/{hero_id}"

    assert client.get(url).status_code == 401
    assert client.get(url, headers={"X-Client-Id": str(hero_id)}).status_code == 401
    assert client.get(url, headers={"X-Client-Id": "not-a-uuid", "X-Client-Role": "hero"}).status_code == 401
    assert client.get(url, headers={"X-Client-Id": str(hero_id), "X-Client-Role": "admin"}).status_code == 401

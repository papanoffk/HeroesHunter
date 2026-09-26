from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from corporations.schemas import Role

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff" + b"\x00" * 16

HeadersFactory = Callable[..., dict[str, str]]


def create_corp(
    client: TestClient, headers: dict[str, str], client_uuid: UUID, image: bytes | None = None, **fields: str
):
    data = {"client_uuid": str(client_uuid), "name": "Stark Industries", "description": "Weapons and tech", **fields}
    files = {"image": ("logo.png", image, "image/png")} if image else None
    return client.post("/v1/corporations", data=data, files=files, headers=headers)


@pytest.fixture
def corp_id(client: TestClient, make_headers: HeadersFactory) -> UUID:
    corp_id = uuid4()
    assert create_corp(client, make_headers(corp_id), corp_id, PNG).status_code == 201
    return corp_id


def test_create_corporation(client: TestClient, make_headers: HeadersFactory) -> None:
    corp_id = uuid4()

    response = create_corp(client, make_headers(corp_id), corp_id, PNG)

    assert response.status_code == 201
    assert response.json() == {
        "client_uuid": str(corp_id),
        "name": "Stark Industries",
        "description": "Weapons and tech",
        "image_url": f"/v1/corporations/{corp_id}/image",
    }


def test_create_corporation_with_only_name(client: TestClient, make_headers: HeadersFactory) -> None:
    corp_id = uuid4()

    response = client.post(
        "/v1/corporations", data={"client_uuid": str(corp_id), "name": "Umbrella"}, headers=make_headers(corp_id)
    )

    assert response.status_code == 201
    assert response.json()["description"] is None
    assert response.json()["image_url"] is None


def test_create_corporation_duplicate_returns_409(
    client: TestClient, make_headers: HeadersFactory, corp_id: UUID
) -> None:
    assert create_corp(client, make_headers(corp_id), corp_id).status_code == 409


def test_create_corporation_access(client: TestClient, make_headers: HeadersFactory) -> None:
    corp_id = uuid4()

    assert create_corp(client, make_headers(uuid4()), corp_id).status_code == 403
    assert create_corp(client, make_headers(corp_id, Role.HERO), corp_id).status_code == 403
    assert create_corp(client, {}, corp_id).status_code == 401


def test_create_corporation_validation(client: TestClient, make_headers: HeadersFactory) -> None:
    corp_id = uuid4()
    headers = make_headers(corp_id)

    assert create_corp(client, headers, corp_id, name="").status_code == 422
    assert create_corp(client, headers, corp_id, name="x" * 151).status_code == 422
    assert create_corp(client, headers, corp_id, b"not an image").status_code == 415
    assert create_corp(client, headers, corp_id, PNG + b"\x00" * 2048).status_code == 413


def test_get_corporation_only_for_owner(client: TestClient, make_headers: HeadersFactory, corp_id: UUID) -> None:
    url = f"/v1/corporations/{corp_id}"

    assert client.get(url, headers=make_headers(corp_id)).json()["name"] == "Stark Industries"
    assert client.get(url, headers=make_headers(uuid4())).status_code == 403
    assert client.get(url).status_code == 401


def test_get_missing_corporation_returns_404(client: TestClient, make_headers: HeadersFactory) -> None:
    corp_id = uuid4()

    assert client.get(f"/v1/corporations/{corp_id}", headers=make_headers(corp_id)).status_code == 404


def test_get_corporation_image(client: TestClient, make_headers: HeadersFactory, corp_id: UUID) -> None:
    response = client.get(f"/v1/corporations/{corp_id}/image", headers=make_headers(corp_id))

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == PNG
    assert client.get(f"/v1/corporations/{corp_id}/image", headers=make_headers(uuid4())).status_code == 403


def test_update_corporation(client: TestClient, make_headers: HeadersFactory, corp_id: UUID) -> None:
    url = f"/v1/corporations/{corp_id}"
    headers = make_headers(corp_id)

    described = client.patch(url, data={"description": "Clean energy"}, headers=headers)
    new_image = client.patch(url, files={"image": ("logo.jpg", JPEG, "image/jpeg")}, headers=headers)

    assert described.status_code == 200
    assert described.json()["description"] == "Clean energy"
    assert described.json()["name"] == "Stark Industries"
    assert new_image.status_code == 200
    assert new_image.json()["description"] == "Clean energy"
    assert client.get(f"{url}/image", headers=headers).headers["content-type"] == "image/jpeg"


def test_update_validation_and_access(client: TestClient, make_headers: HeadersFactory, corp_id: UUID) -> None:
    url = f"/v1/corporations/{corp_id}"
    missing = uuid4()

    assert client.patch(url, headers=make_headers(corp_id)).status_code == 422
    assert client.patch(url, data={"name": ""}, headers=make_headers(corp_id)).status_code == 422
    assert client.patch(url, data={"name": "X"}, headers=make_headers(uuid4())).status_code == 403
    assert client.patch(f"/v1/corporations/{missing}", data={"name": "X"}, headers=make_headers(missing)).status_code == 404


def test_missing_or_invalid_gateway_headers_return_401(client: TestClient, corp_id: UUID) -> None:
    url = f"/v1/corporations/{corp_id}"

    assert client.get(url, headers={"X-Client-Id": str(corp_id)}).status_code == 401
    assert client.get(url, headers={"X-Client-Id": "not-a-uuid", "X-Client-Role": "corporation"}).status_code == 401

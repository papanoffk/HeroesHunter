from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from fastapi import Depends
from fastapi.testclient import TestClient

from auth.config import Settings
from auth.dependencies import require_roles
from auth.schemas import Role
from auth.security import create_access_token

CREDS = {"email": "Hero@Example.com", "password": "strong-password", "role": "hero"}


def register_and_login(client: TestClient) -> str:
    assert client.post("/auth/register", json=CREDS).status_code == 201
    response = client.post("/auth/login", json=CREDS)
    assert response.status_code == 200
    return response.json()["access_token"]


def test_register_normalizes_email(client: TestClient) -> None:
    response = client.post("/auth/register", json=CREDS)

    assert response.status_code == 201
    assert response.json()["email"] == "hero@example.com"
    assert "pass_hash" not in response.json()


def test_register_duplicate_returns_409(client: TestClient) -> None:
    client.post("/auth/register", json=CREDS)

    assert client.post("/auth/register", json=CREDS).status_code == 409


def test_same_email_allowed_for_different_roles(client: TestClient) -> None:
    client.post("/auth/register", json=CREDS)

    response = client.post("/auth/register", json=CREDS | {"role": "corporation"})

    assert response.status_code == 201


def test_register_rejects_unknown_role_and_short_password(client: TestClient) -> None:
    assert client.post("/auth/register", json=CREDS | {"role": "admin"}).status_code == 422
    assert client.post("/auth/register", json=CREDS | {"password": "short"}).status_code == 422


def test_login_token_payload(client: TestClient, settings: Settings) -> None:
    token = register_and_login(client)

    payload = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"])

    assert set(payload) == {"client_id", "role", "exp"}
    assert payload["role"] == "hero"


def test_login_wrong_password_or_role_returns_401(client: TestClient) -> None:
    client.post("/auth/register", json=CREDS)

    assert client.post("/auth/login", json=CREDS | {"password": "wrong-password"}).status_code == 401
    assert client.post("/auth/login", json=CREDS | {"role": "corporation"}).status_code == 401


def test_me_returns_current_client(client: TestClient) -> None:
    token = register_and_login(client)

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "hero@example.com"


def test_me_rejects_missing_invalid_and_expired_tokens(client: TestClient, settings: Settings) -> None:
    expired = jwt.encode(
        {"client_id": str(uuid4()), "role": "hero", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret.get_secret_value(),
    )

    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_require_roles(client: TestClient, settings: Settings) -> None:
    @client.app.get("/corp-only", dependencies=[Depends(require_roles(Role.CORPORATION))])
    async def corp_only() -> dict[str, bool]:
        return {"ok": True}

    hero = create_access_token(uuid4(), Role.HERO, settings)
    corp = create_access_token(uuid4(), Role.CORPORATION, settings)

    assert client.get("/corp-only", headers={"Authorization": f"Bearer {hero}"}).status_code == 403
    assert client.get("/corp-only", headers={"Authorization": f"Bearer {corp}"}).status_code == 200

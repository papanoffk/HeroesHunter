from fastapi import APIRouter, HTTPException, Response, status

from auth.dependencies import ClientRepositoryDep, SettingsDep, TokenPayloadDep
from auth.repository import Client, ClientAlreadyExistsError
from auth.schemas import ClientResponse, LoginRequest, RegisterRequest, TokenPayload, TokenResponse
from auth.security import DUMMY_HASH, create_access_token, password_hash

router = APIRouter(prefix="/auth", tags=["auth"])

CLIENT_ID_HEADER = "X-Client-Id"
CLIENT_ROLE_HEADER = "X-Client-Role"


def to_response(client: Client) -> ClientResponse:
    return ClientResponse(
        client_id=client.client_uuid, email=client.email, role=client.role, created_at=client.created_at
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, repo: ClientRepositoryDep) -> ClientResponse:
    try:
        client = await repo.create(body.email, password_hash.hash(body.password), body.role)
    except ClientAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Client with this email and role already exists"
        ) from None
    return to_response(client)


@router.post("/login")
async def login(body: LoginRequest, repo: ClientRepositoryDep, settings: SettingsDep) -> TokenResponse:
    client = await repo.get_by_email(body.email, body.role)
    is_valid = password_hash.verify(body.password, client.pass_hash if client else DUMMY_HASH)
    if client is None or not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email, password or role",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(client.client_uuid, client.role, settings),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.get("/me")
async def me(payload: TokenPayloadDep, repo: ClientRepositoryDep) -> ClientResponse:
    client = await repo.get_by_id(payload.client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return to_response(client)


@router.get("/verify", status_code=status.HTTP_200_OK)
async def verify(payload: TokenPayloadDep, response: Response) -> TokenPayload:
    """Forward auth for the API gateway: identity is passed to services in response headers."""
    response.headers[CLIENT_ID_HEADER] = str(payload.client_id)
    response.headers[CLIENT_ROLE_HEADER] = payload.role.value
    return payload

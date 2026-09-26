from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from heroes.config import Settings
from heroes.dependencies import HeroRepositoryDep, OwnerDep, PowerRepositoryDep, SettingsDep, require_roles
from heroes.repository import Hero, HeroAlreadyExistsError
from heroes.schemas import HeroResponse, PowerResponse, Principal, Role

powers_router = APIRouter(prefix="/v1/heroes/powers", tags=["powers"])
heroes_router = APIRouter(prefix="/v1/heroes", tags=["heroes"])

IMAGE_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
}

HeroName = Annotated[str, Form(min_length=1, max_length=100)]


def detect_image_media_type(data: bytes) -> str | None:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return next((media for sig, media in IMAGE_SIGNATURES.items() if data.startswith(sig)), None)


async def read_image(upload: UploadFile | None, settings: Settings) -> bytes | None:
    if upload is None:
        return None
    data = await upload.read(settings.max_image_size_bytes + 1)
    if len(data) > settings.max_image_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Image must not exceed {settings.max_image_size_bytes} bytes",
        )
    if detect_image_media_type(data) is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Image must be PNG, JPEG, GIF or WebP"
        )
    return data


def to_response(hero: Hero) -> HeroResponse:
    image_url = f"{heroes_router.prefix}/{hero.client_uuid}/image" if hero.has_image else None
    return HeroResponse(client_uuid=hero.client_uuid, name=hero.name, image_url=image_url)


@powers_router.get("")
async def list_powers(repo: PowerRepositoryDep) -> list[PowerResponse]:
    return [PowerResponse(power_id=p.power_id, title=p.title) for p in await repo.list()]


@powers_router.get("/{power_id}")
async def get_power(power_id: int, repo: PowerRepositoryDep) -> PowerResponse:
    power = await repo.get(power_id)
    if power is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Power not found")
    return PowerResponse(power_id=power.power_id, title=power.title)


@heroes_router.post("", status_code=status.HTTP_201_CREATED)
async def create_hero(
    client_uuid: Annotated[UUID, Form()],
    name: HeroName,
    principal: Annotated[Principal, Depends(require_roles(Role.HERO))],
    repo: HeroRepositoryDep,
    settings: SettingsDep,
    image: Annotated[UploadFile | None, File()] = None,
) -> HeroResponse:
    if principal.client_id != client_uuid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hero can be created only for yourself")
    try:
        hero = await repo.create(client_uuid, name, await read_image(image, settings))
    except HeroAlreadyExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Hero already exists") from None
    return to_response(hero)


@heroes_router.get("/{client_uuid}")
async def get_hero(client_uuid: UUID, _: OwnerDep, repo: HeroRepositoryDep) -> HeroResponse:
    hero = await repo.get(client_uuid)
    if hero is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hero not found")
    return to_response(hero)


@heroes_router.patch("/{client_uuid}")
async def update_hero(
    client_uuid: UUID,
    _: OwnerDep,
    repo: HeroRepositoryDep,
    settings: SettingsDep,
    name: Annotated[str | None, Form(min_length=1, max_length=100)] = None,
    image: Annotated[UploadFile | None, File()] = None,
) -> HeroResponse:
    if name is None and image is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Provide at least one of: name, image"
        )
    hero = await repo.update(client_uuid, name, await read_image(image, settings))
    if hero is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hero not found")
    return to_response(hero)


@heroes_router.get(
    "/{client_uuid}/image",
    response_class=Response,
    responses={200: {"content": {"image/*": {}}}},
)
async def get_hero_image(client_uuid: UUID, _: OwnerDep, repo: HeroRepositoryDep) -> Response:
    image = await repo.get_image(client_uuid)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hero image not found")
    return Response(content=image, media_type=detect_image_media_type(image) or "application/octet-stream")

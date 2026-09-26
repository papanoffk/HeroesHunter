from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from corporations.config import Settings
from corporations.dependencies import CorpRepositoryDep, OwnerDep, SettingsDep, require_roles
from corporations.repository import Corp, CorpAlreadyExistsError
from corporations.schemas import CorpResponse, Principal, Role

router = APIRouter(prefix="/v1/corporations", tags=["corporations"])

IMAGE_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
}

CorpName = Annotated[str, Form(min_length=1, max_length=150)]


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


def to_response(corp: Corp) -> CorpResponse:
    image_url = f"{router.prefix}/{corp.client_uuid}/image" if corp.has_image else None
    return CorpResponse(
        client_uuid=corp.client_uuid, name=corp.name, description=corp.description, image_url=image_url
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_corporation(
    client_uuid: Annotated[UUID, Form()],
    name: CorpName,
    principal: Annotated[Principal, Depends(require_roles(Role.CORPORATION))],
    repo: CorpRepositoryDep,
    settings: SettingsDep,
    description: Annotated[str | None, Form()] = None,
    image: Annotated[UploadFile | None, File()] = None,
) -> CorpResponse:
    if principal.client_id != client_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Corporation can be created only for yourself"
        )
    try:
        corp = await repo.create(client_uuid, name, description, await read_image(image, settings))
    except CorpAlreadyExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Corporation already exists") from None
    return to_response(corp)


@router.get("/{client_uuid}")
async def get_corporation(client_uuid: UUID, _: OwnerDep, repo: CorpRepositoryDep) -> CorpResponse:
    corp = await repo.get(client_uuid)
    if corp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corporation not found")
    return to_response(corp)


@router.patch("/{client_uuid}")
async def update_corporation(
    client_uuid: UUID,
    _: OwnerDep,
    repo: CorpRepositoryDep,
    settings: SettingsDep,
    name: Annotated[str | None, Form(min_length=1, max_length=150)] = None,
    description: Annotated[str | None, Form()] = None,
    image: Annotated[UploadFile | None, File()] = None,
) -> CorpResponse:
    if name is None and description is None and image is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide at least one of: name, description, image",
        )
    corp = await repo.update(client_uuid, name, description, await read_image(image, settings))
    if corp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corporation not found")
    return to_response(corp)


@router.get(
    "/{client_uuid}/image",
    response_class=Response,
    responses={200: {"content": {"image/*": {}}}},
)
async def get_corporation_image(client_uuid: UUID, _: OwnerDep, repo: CorpRepositoryDep) -> Response:
    image = await repo.get_image(client_uuid)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corporation image not found")
    return Response(content=image, media_type=detect_image_media_type(image) or "application/octet-stream")

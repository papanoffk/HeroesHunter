from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status

from missions.dependencies import (
    MissionRepositoryDep,
    OptionalPrincipalDep,
    OwnedMissionDep,
    PublisherDep,
    require_roles,
)
from missions.events import MISSION_RESPONDED
from missions.repository import AlreadyRespondedError, Mission, MissionNotFoundError
from missions.schemas import (
    CreateMissionRequest,
    MissionFilters,
    MissionResponse,
    Principal,
    Role,
    UpdateMissionRequest,
    ViewRequest,
)

router = APIRouter(prefix="/v1/missions", tags=["missions"])

NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found")


def to_response(mission: Mission, principal: Principal | None) -> MissionResponse:
    response = MissionResponse(
        missions_uuid=mission.missions_uuid,
        owner_uuid=mission.owner_uuid,
        title=mission.title,
        descriptions=mission.descriptions,
        location=mission.location,
        powers_ids=mission.powers_ids,
        work_experience=mission.work_experience,
        offer=mission.offer,
        created_at=mission.created_at,
    )
    if principal is not None and principal.client_id == mission.owner_uuid:
        response.respondents_uuids = mission.respondents_uuids
        response.new_respondents_uuids = mission.new_respondents_uuids
    return response


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_mission(
    body: CreateMissionRequest,
    principal: Annotated[Principal, Depends(require_roles(Role.CORPORATION))],
    repo: MissionRepositoryDep,
) -> MissionResponse:
    mission = await repo.create(principal.client_id, body.model_dump())
    return to_response(mission, principal)


@router.get("")
async def list_missions(
    filters: Annotated[MissionFilters, Query()], principal: OptionalPrincipalDep, repo: MissionRepositoryDep
) -> list[MissionResponse]:
    return [to_response(mission, principal) for mission in await repo.search(filters)]


@router.get("/{mission_uuid}")
async def get_mission(
    mission_uuid: UUID, principal: OptionalPrincipalDep, repo: MissionRepositoryDep
) -> MissionResponse:
    mission = await repo.get(mission_uuid)
    if mission is None:
        raise NOT_FOUND
    return to_response(mission, principal)


@router.patch("/{mission_uuid}")
async def update_mission(
    body: UpdateMissionRequest, mission: OwnedMissionDep, repo: MissionRepositoryDep
) -> MissionResponse:
    updated = await repo.update(mission.missions_uuid, body.model_dump(exclude_unset=True))
    if updated is None:
        raise NOT_FOUND
    return to_response(updated, Principal(client_id=mission.owner_uuid, role=Role.CORPORATION))


@router.delete("/{mission_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mission(mission: OwnedMissionDep, repo: MissionRepositoryDep) -> Response:
    if not await repo.delete(mission.missions_uuid):
        raise NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{mission_uuid}/view")
async def view_respondents(
    body: ViewRequest, mission: OwnedMissionDep, repo: MissionRepositoryDep
) -> MissionResponse:
    updated = await repo.mark_viewed(mission.missions_uuid, body.respondents_uuids)
    if updated is None:
        raise NOT_FOUND
    return to_response(updated, Principal(client_id=mission.owner_uuid, role=Role.CORPORATION))


@router.post("/{mission_uuid}/respond", status_code=status.HTTP_204_NO_CONTENT)
async def respond(
    mission_uuid: UUID,
    principal: Annotated[Principal, Depends(require_roles(Role.HERO))],
    repo: MissionRepositoryDep,
    publisher: PublisherDep,
    background_tasks: BackgroundTasks,
) -> Response:
    try:
        owner_uuid = await repo.respond(mission_uuid, principal.client_id)
    except MissionNotFoundError:
        raise NOT_FOUND from None
    except AlreadyRespondedError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already responded") from None
    # Sent after the response: the response is already stored, a notification is best-effort.
    background_tasks.add_task(
        publisher.publish,
        MISSION_RESPONDED,
        {"recipient_uuid": owner_uuid, "mission_uuid": mission_uuid, "hero_uuid": principal.client_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status

from resumes.dependencies import (
    OptionalPrincipalDep,
    OwnedResumeDep,
    PublisherDep,
    ResumeRepositoryDep,
    require_roles,
)
from resumes.events import RESUME_INVITED
from resumes.repository import AlreadyInvitedError, Resume, ResumeNotFoundError
from resumes.schemas import (
    CreateResumeRequest,
    Principal,
    ResumeFilters,
    ResumeResponse,
    Role,
    UpdateResumeRequest,
    ViewRequest,
)

router = APIRouter(prefix="/v1/resumes", tags=["resumes"])

NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")


def to_response(resume: Resume, principal: Principal | None) -> ResumeResponse:
    response = ResumeResponse(
        resume_uuid=resume.resume_uuid,
        owner_uuid=resume.owner_uuid,
        title=resume.title,
        descriptions=resume.descriptions,
        previous_works=resume.previous_works,
        powers_ids=resume.powers_ids,
        work_experience=resume.work_experience,
        offer=resume.offer,
        created_at=resume.created_at,
    )
    if principal is not None and principal.client_id == resume.owner_uuid:
        response.invitations_corp_uuids = resume.invitations_corp_uuids
        response.new_invitations_corp_uuids = resume.new_invitations_corp_uuids
    return response


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_resume(
    body: CreateResumeRequest,
    principal: Annotated[Principal, Depends(require_roles(Role.HERO))],
    repo: ResumeRepositoryDep,
) -> ResumeResponse:
    resume = await repo.create(principal.client_id, body.model_dump())
    return to_response(resume, principal)


@router.get("")
async def list_resumes(
    filters: Annotated[ResumeFilters, Query()], principal: OptionalPrincipalDep, repo: ResumeRepositoryDep
) -> list[ResumeResponse]:
    return [to_response(resume, principal) for resume in await repo.search(filters)]


@router.get("/{resume_uuid}")
async def get_resume(resume_uuid: UUID, principal: OptionalPrincipalDep, repo: ResumeRepositoryDep) -> ResumeResponse:
    resume = await repo.get(resume_uuid)
    if resume is None:
        raise NOT_FOUND
    return to_response(resume, principal)


@router.patch("/{resume_uuid}")
async def update_resume(body: UpdateResumeRequest, resume: OwnedResumeDep, repo: ResumeRepositoryDep) -> ResumeResponse:
    updated = await repo.update(resume.resume_uuid, body.model_dump(exclude_unset=True))
    if updated is None:
        raise NOT_FOUND
    return to_response(updated, Principal(client_id=resume.owner_uuid, role=Role.HERO))


@router.delete("/{resume_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(resume: OwnedResumeDep, repo: ResumeRepositoryDep) -> Response:
    if not await repo.delete(resume.resume_uuid):
        raise NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{resume_uuid}/view")
async def view_invitations(body: ViewRequest, resume: OwnedResumeDep, repo: ResumeRepositoryDep) -> ResumeResponse:
    updated = await repo.mark_viewed(resume.resume_uuid, body.invitations_corp_uuids)
    if updated is None:
        raise NOT_FOUND
    return to_response(updated, Principal(client_id=resume.owner_uuid, role=Role.HERO))


@router.post("/{resume_uuid}/invitation", status_code=status.HTTP_204_NO_CONTENT)
async def invite(
    resume_uuid: UUID,
    principal: Annotated[Principal, Depends(require_roles(Role.CORPORATION))],
    repo: ResumeRepositoryDep,
    publisher: PublisherDep,
    background_tasks: BackgroundTasks,
) -> Response:
    try:
        owner_uuid = await repo.invite(resume_uuid, principal.client_id)
    except ResumeNotFoundError:
        raise NOT_FOUND from None
    except AlreadyInvitedError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already invited") from None
    # Sent after the response: the invitation is already stored, a notification is best-effort.
    background_tasks.add_task(
        publisher.publish,
        RESUME_INVITED,
        {"recipient_uuid": owner_uuid, "resume_uuid": resume_uuid, "corp_uuid": principal.client_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

"""Organization CRUD.

No access control yet — anyone can create/list/delete any organization.
This is intentionally wide open until Milestone 2's auth (roadmap steps
060+) adds real authentication and authorization; wiring these routes
behind auth is tracked there, not silently deferred. Do not deploy this
outside local development before that lands.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db
from errors import ConflictError, NotFoundError
from repositories.organization import OrganizationRepository
from schemas.common import Page, PaginationParams
from schemas.organization import OrganizationCreate, OrganizationRead

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=201)
async def create_organization(
    body: OrganizationCreate, session: Annotated[AsyncSession, Depends(get_db)]
) -> OrganizationRead:
    repo = OrganizationRepository(session)
    try:
        org = await repo.create(name=body.name, slug=body.slug)
    except IntegrityError as exc:
        raise ConflictError(f"An organization with slug '{body.slug}' already exists.") from exc
    return OrganizationRead.model_validate(org)


@router.get("", response_model=Page[OrganizationRead])
async def list_organizations(
    session: Annotated[AsyncSession, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
) -> Page[OrganizationRead]:
    repo = OrganizationRepository(session)
    orgs = await repo.list(limit=pagination.limit, offset=pagination.offset)
    total = await repo.count()
    return Page(
        items=[OrganizationRead.model_validate(o) for o in orgs],
        limit=pagination.limit,
        offset=pagination.offset,
        total=total,
    )


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization(
    organization_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> OrganizationRead:
    repo = OrganizationRepository(session)
    org = await repo.get(organization_id)
    if org is None:
        raise NotFoundError(f"Organization {organization_id} not found.")
    return OrganizationRead.model_validate(org)


@router.delete("/{organization_id}", status_code=204)
async def delete_organization(
    organization_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    repo = OrganizationRepository(session)
    org = await repo.get(organization_id)
    if org is None:
        raise NotFoundError(f"Organization {organization_id} not found.")
    await repo.delete(org)

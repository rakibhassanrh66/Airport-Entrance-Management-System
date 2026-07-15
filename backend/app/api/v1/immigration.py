from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, RequireSecurity, SessionDep
from app.api.v1._pagination import paginate
from app.models.enums import ImmigrationStatus
from app.models.operations import Immigration
from app.schemas.common import Page
from app.schemas.operations import ImmigrationCreate, ImmigrationDecision, ImmigrationOut
from app.services import immigration as immigration_service

router = APIRouter(prefix="/immigration", tags=["immigration"])


@router.get("", response_model=Page[ImmigrationOut], summary="List immigration cases")
async def list_cases(
    session: SessionDep,
    _: CurrentUser,
    status_filter: Annotated[ImmigrationStatus | None, Query(alias="status")] = None,
    flight_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ImmigrationOut]:
    stmt = select(Immigration)
    if status_filter is not None:
        stmt = stmt.where(Immigration.status == status_filter)
    if flight_id is not None:
        stmt = stmt.where(Immigration.flight_id == flight_id)
    return await paginate(
        session,
        stmt,
        schema=ImmigrationOut,
        limit=limit,
        offset=offset,
        order_by=Immigration.id,
    )


@router.post(
    "",
    response_model=ImmigrationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Open an immigration case",
    description="Requires the passenger to hold a live ticket on the flight.",
)
async def open_case(
    payload: ImmigrationCreate, session: SessionDep, _: RequireSecurity
) -> ImmigrationOut:
    case = await immigration_service.open_case(session, payload)
    return ImmigrationOut.model_validate(case)


@router.get("/{case_id}", response_model=ImmigrationOut, summary="Fetch one case")
async def get_case(case_id: int, session: SessionDep, _: CurrentUser) -> ImmigrationOut:
    case = await immigration_service.get_case(session, case_id)
    return ImmigrationOut.model_validate(case)


@router.post(
    "/{case_id}/decision",
    response_model=ImmigrationOut,
    summary="Approve or reject a case",
)
async def decide(
    case_id: int, payload: ImmigrationDecision, session: SessionDep, _: RequireSecurity
) -> ImmigrationOut:
    case = await immigration_service.decide(session, case_id, payload)
    return ImmigrationOut.model_validate(case)

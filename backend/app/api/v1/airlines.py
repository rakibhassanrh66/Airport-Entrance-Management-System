from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, RequireOps, SessionDep
from app.api.v1._pagination import paginate
from app.core.errors import ConflictError, NotFoundError
from app.models.operations import Airline, AirlineStaff
from app.schemas.common import Page
from app.schemas.operations import (
    AirlineCreate,
    AirlineOut,
    AirlineStaffCreate,
    AirlineStaffOut,
)

router = APIRouter(prefix="/airlines", tags=["airlines"])


async def _require_airline(session: SessionDep, airline_id: int) -> Airline:
    airline = await session.get(Airline, airline_id)
    if airline is None:
        raise NotFoundError(f"Airline {airline_id} not found.")
    return airline


@router.get("", response_model=Page[AirlineOut], summary="List airlines")
async def list_airlines(
    session: SessionDep,
    _: CurrentUser,
    country: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AirlineOut]:
    stmt = select(Airline)
    if country is not None:
        stmt = stmt.where(Airline.country.ilike(country.strip()))
    return await paginate(
        session, stmt, schema=AirlineOut, limit=limit, offset=offset, order_by=Airline.name
    )


@router.post(
    "", response_model=AirlineOut, status_code=status.HTTP_201_CREATED, summary="Add an airline"
)
async def create_airline(payload: AirlineCreate, session: SessionDep, _: RequireOps) -> AirlineOut:
    airline = Airline(**payload.model_dump())
    session.add(airline)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(f"IATA code {payload.iata_code!r} is already registered.") from exc

    await session.refresh(airline)
    return AirlineOut.model_validate(airline)


@router.get("/{airline_id}", response_model=AirlineOut, summary="Fetch one airline")
async def get_airline(airline_id: int, session: SessionDep, _: CurrentUser) -> AirlineOut:
    return AirlineOut.model_validate(await _require_airline(session, airline_id))


@router.get(
    "/{airline_id}/staff",
    response_model=Page[AirlineStaffOut],
    summary="List an airline's staff",
)
async def list_airline_staff(
    airline_id: int,
    session: SessionDep,
    _: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AirlineStaffOut]:
    await _require_airline(session, airline_id)
    return await paginate(
        session,
        select(AirlineStaff).where(AirlineStaff.airline_id == airline_id),
        schema=AirlineStaffOut,
        limit=limit,
        offset=offset,
        order_by=AirlineStaff.name,
    )


@router.post(
    "/{airline_id}/staff",
    response_model=AirlineStaffOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a staff member to an airline",
)
async def create_airline_staff(
    airline_id: int, payload: AirlineStaffCreate, session: SessionDep, _: RequireOps
) -> AirlineStaffOut:
    await _require_airline(session, airline_id)
    member = AirlineStaff(airline_id=airline_id, **payload.model_dump())
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return AirlineStaffOut.model_validate(member)

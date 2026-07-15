from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, RequireOps, SessionDep
from app.api.v1._pagination import paginate
from app.core.errors import ConflictError, NotFoundError
from app.models.operations import Airline
from app.schemas.common import Page
from app.schemas.operations import AirlineCreate, AirlineOut

router = APIRouter(prefix="/airlines", tags=["airlines"])


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
    airline = await session.get(Airline, airline_id)
    if airline is None:
        raise NotFoundError(f"Airline {airline_id} not found.")
    return AirlineOut.model_validate(airline)

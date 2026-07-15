from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, RequireCheckin, SessionDep
from app.api.v1._pagination import paginate
from app.core.errors import ConflictError, NotFoundError
from app.models.operations import Passenger
from app.schemas.common import Page
from app.schemas.operations import PassengerCreate, PassengerOut

router = APIRouter(prefix="/passengers", tags=["passengers"])


@router.get("", response_model=Page[PassengerOut], summary="List passengers")
async def list_passengers(
    session: SessionDep,
    _: CurrentUser,
    last_name: Annotated[str | None, Query(max_length=50)] = None,
    nationality: Annotated[str | None, Query(max_length=50)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[PassengerOut]:
    stmt = select(Passenger)
    if last_name is not None:
        stmt = stmt.where(Passenger.last_name.ilike(f"{last_name.strip()}%"))
    if nationality is not None:
        stmt = stmt.where(Passenger.nationality.ilike(nationality.strip()))
    return await paginate(
        session,
        stmt,
        schema=PassengerOut,
        limit=limit,
        offset=offset,
        order_by=Passenger.last_name,
    )


@router.post(
    "",
    response_model=PassengerOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a passenger",
)
async def create_passenger(
    payload: PassengerCreate, session: SessionDep, _: RequireCheckin
) -> PassengerOut:
    passenger = Passenger(**payload.model_dump())
    session.add(passenger)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(f"Passport {payload.passport_number!r} is already registered.") from exc

    await session.refresh(passenger)
    return PassengerOut.model_validate(passenger)


@router.get("/{passenger_id}", response_model=PassengerOut, summary="Fetch one passenger")
async def get_passenger(passenger_id: int, session: SessionDep, _: CurrentUser) -> PassengerOut:
    passenger = await session.get(Passenger, passenger_id)
    if passenger is None:
        raise NotFoundError(f"Passenger {passenger_id} not found.")
    return PassengerOut.model_validate(passenger)

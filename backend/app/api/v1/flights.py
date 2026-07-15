from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, RequireOps, SessionDep
from app.api.v1._pagination import paginate
from app.models.enums import FlightStatus
from app.schemas.common import Page
from app.schemas.operations import (
    FlightCreate,
    FlightOut,
    FlightSeatMap,
    FlightStatusUpdate,
)
from app.services import flights as flight_service

router = APIRouter(prefix="/flights", tags=["flights"])


@router.get("", response_model=Page[FlightOut], summary="List flights")
async def list_flights(
    session: SessionDep,
    _: CurrentUser,
    status_filter: Annotated[FlightStatus | None, Query(alias="status")] = None,
    airline_id: Annotated[int | None, Query()] = None,
    destination: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[FlightOut]:
    stmt = flight_service.build_flight_query(
        status=status_filter, airline_id=airline_id, destination=destination
    )
    from app.models.operations import Flight

    return await paginate(
        session,
        stmt,
        schema=FlightOut,
        limit=limit,
        offset=offset,
        order_by=Flight.departure_time,
    )


@router.post(
    "",
    response_model=FlightOut,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a flight",
)
async def create_flight(payload: FlightCreate, session: SessionDep, _: RequireOps) -> FlightOut:
    flight = await flight_service.create_flight(session, payload)
    return FlightOut.model_validate(flight)


@router.get("/{flight_id}", response_model=FlightOut, summary="Fetch one flight")
async def get_flight(flight_id: int, session: SessionDep, _: CurrentUser) -> FlightOut:
    flight = await flight_service.get_flight(session, flight_id)
    return FlightOut.model_validate(flight)


@router.patch(
    "/{flight_id}/status",
    response_model=FlightOut,
    summary="Move a flight through its lifecycle",
    description=(
        "Only legal transitions are accepted. Cancelling a flight also cancels its "
        "live tickets and releases its gate assignments."
    ),
)
async def change_status(
    flight_id: int, payload: FlightStatusUpdate, session: SessionDep, _: RequireOps
) -> FlightOut:
    flight = await flight_service.change_status(session, flight_id, payload.status)
    return FlightOut.model_validate(flight)


@router.get(
    "/{flight_id}/seats",
    response_model=FlightSeatMap,
    summary="Which seats are taken on this flight",
)
async def seat_map(flight_id: int, session: SessionDep, _: CurrentUser) -> FlightSeatMap:
    return await flight_service.seat_map(session, flight_id)

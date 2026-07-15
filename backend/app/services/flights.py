import logging
from datetime import UTC, datetime

from sqlalchemy import Select, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, IllegalStateTransitionError, NotFoundError
from app.models.enums import (
    ACTIVE_BOOKING_STATUSES,
    FLIGHT_STATUS_TRANSITIONS,
    BookingStatus,
    FlightStatus,
)
from app.models.operations import Airline, Flight, GateAssignment, Ticket
from app.schemas.operations import FlightCreate, FlightSeatMap

logger = logging.getLogger(__name__)

#: Flights in these states still accept new bookings.
BOOKABLE_STATUSES = frozenset({FlightStatus.SCHEDULED, FlightStatus.DELAYED, FlightStatus.BOARDING})


async def get_flight(session: AsyncSession, flight_id: int) -> Flight:
    flight = await session.get(Flight, flight_id)
    if flight is None:
        raise NotFoundError(f"Flight {flight_id} not found.")
    return flight


async def create_flight(session: AsyncSession, payload: FlightCreate) -> Flight:
    airline = await session.get(Airline, payload.airline_id)
    if airline is None:
        raise NotFoundError(f"Airline {payload.airline_id} not found.")

    flight = Flight(**payload.model_dump(), status=FlightStatus.SCHEDULED)
    session.add(flight)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(f"Flight number {payload.flight_number!r} is already in use.") from exc

    await session.refresh(flight)
    return flight


def build_flight_query(
    *,
    status: FlightStatus | None = None,
    airline_id: int | None = None,
    destination: str | None = None,
) -> Select[tuple[Flight]]:
    stmt = select(Flight)
    if status is not None:
        stmt = stmt.where(Flight.status == status)
    if airline_id is not None:
        stmt = stmt.where(Flight.airline_id == airline_id)
    if destination is not None:
        # Parameterised: the original PHP concatenated user input straight into SQL.
        stmt = stmt.where(func.lower(Flight.destination) == destination.strip().lower())
    return stmt


async def change_status(session: AsyncSession, flight_id: int, new_status: FlightStatus) -> Flight:
    """Move a flight through its lifecycle, rejecting illegal jumps.

    Cancelling cascades: a cancelled flight must not leave live tickets or a
    gate reserved, or the gate stays blocked for every other flight.
    """
    flight = await get_flight(session, flight_id)
    current = flight.status

    allowed = FLIGHT_STATUS_TRANSITIONS[current]
    if new_status not in allowed:
        raise IllegalStateTransitionError(
            entity=f"flight {flight.flight_number}",
            current=current.value,
            requested=new_status.value,
            allowed=sorted(s.value for s in allowed),
        )

    flight.status = new_status

    if new_status is FlightStatus.CANCELLED:
        cancelled_tickets = await _cancel_tickets_for_flight(session, flight_id)
        released_gates = await _release_gate_assignments(session, flight_id)
        logger.info(
            "flight cancelled",
            extra={
                "flight_id": flight_id,
                "tickets_cancelled": cancelled_tickets,
                "gate_assignments_released": released_gates,
            },
        )

    await session.commit()
    await session.refresh(flight)
    return flight


async def _cancel_tickets_for_flight(session: AsyncSession, flight_id: int) -> int:
    result = await session.execute(
        update(Ticket)
        .where(
            Ticket.flight_id == flight_id,
            Ticket.booking_status.in_(ACTIVE_BOOKING_STATUSES),
        )
        # checked_in_at must be cleared to satisfy ck_tickets_checked_in_at_matches_status.
        .values(booking_status=BookingStatus.CANCELLED, checked_in_at=None)
    )
    return result.rowcount or 0


async def _release_gate_assignments(session: AsyncSession, flight_id: int) -> int:
    result = await session.execute(
        update(GateAssignment)
        .where(GateAssignment.flight_id == flight_id, GateAssignment.cancelled_at.is_(None))
        .values(cancelled_at=datetime.now(UTC))
    )
    return result.rowcount or 0


async def seat_map(session: AsyncSession, flight_id: int) -> FlightSeatMap:
    flight = await get_flight(session, flight_id)

    booked = await session.scalars(
        select(Ticket.seat_number)
        .where(
            Ticket.flight_id == flight_id,
            Ticket.booking_status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .order_by(Ticket.seat_number)
    )
    seats = list(booked)

    return FlightSeatMap(
        flight_id=flight.id,
        seat_capacity=flight.seat_capacity,
        booked_seats=seats,
        seats_available=flight.seat_capacity - len(seats),
    )

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models.enums import ACTIVE_BOOKING_STATUSES, BookingStatus
from app.models.operations import Flight, Passenger, Ticket
from app.schemas.operations import TicketCreate
from app.services.flights import BOOKABLE_STATUSES

logger = logging.getLogger(__name__)


async def get_ticket(session: AsyncSession, ticket_id: int) -> Ticket:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise NotFoundError(f"Ticket {ticket_id} not found.")
    return ticket


async def book_ticket(session: AsyncSession, payload: TicketCreate) -> Ticket:
    """Book a seat.

    Correctness here rests on two things the original project had neither of:

    1. The flight row is locked FOR UPDATE, so two concurrent bookings cannot
       both read "179 of 180 sold" and both proceed.
    2. The seat itself is protected by a partial unique index, so even if the
       lock were removed, the database would still refuse a duplicate seat.
    """
    flight = await session.scalar(
        select(Flight).where(Flight.id == payload.flight_id).with_for_update()
    )
    if flight is None:
        raise NotFoundError(f"Flight {payload.flight_id} not found.")

    if flight.status not in BOOKABLE_STATUSES:
        raise ConflictError(
            f"Flight {flight.flight_number} is {flight.status.value}; "
            f"it is not accepting bookings.",
            details={"flight_status": flight.status.value},
        )

    passenger = await session.get(Passenger, payload.passenger_id)
    if passenger is None:
        raise NotFoundError(f"Passenger {payload.passenger_id} not found.")

    await _reject_duplicate_booking(session, payload.flight_id, payload.passenger_id)
    await _reject_if_full(session, flight)

    ticket = Ticket(
        flight_id=payload.flight_id,
        passenger_id=payload.passenger_id,
        seat_number=payload.seat_number,
        ticket_class=payload.ticket_class,
        price=payload.price,
        booking_status=BookingStatus.CONFIRMED,
    )
    session.add(ticket)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_tickets_flight_seat_active" in str(exc.orig):
            raise ConflictError(
                f"Seat {payload.seat_number} is already taken on this flight.",
                details={"seat_number": payload.seat_number},
            ) from exc
        raise

    await session.refresh(ticket)
    logger.info(
        "ticket booked",
        extra={
            "ticket_id": ticket.id,
            "flight_id": ticket.flight_id,
            "seat_number": ticket.seat_number,
        },
    )
    return ticket


async def _reject_duplicate_booking(
    session: AsyncSession, flight_id: int, passenger_id: int
) -> None:
    existing = await session.scalar(
        select(Ticket.id).where(
            Ticket.flight_id == flight_id,
            Ticket.passenger_id == passenger_id,
            Ticket.booking_status.in_(ACTIVE_BOOKING_STATUSES),
        )
    )
    if existing is not None:
        raise ConflictError(
            "This passenger already holds a live ticket on this flight.",
            details={"existing_ticket_id": existing},
        )


async def _reject_if_full(session: AsyncSession, flight: Flight) -> None:
    booked = await session.scalar(
        select(func.count(Ticket.id)).where(
            Ticket.flight_id == flight.id,
            Ticket.booking_status.in_(ACTIVE_BOOKING_STATUSES),
        )
    )
    if (booked or 0) >= flight.seat_capacity:
        raise ConflictError(
            f"Flight {flight.flight_number} is fully booked.",
            details={"seat_capacity": flight.seat_capacity},
        )


async def check_in(session: AsyncSession, ticket_id: int) -> Ticket:
    ticket = await get_ticket(session, ticket_id)

    if ticket.booking_status is BookingStatus.CHECKED_IN:
        raise ConflictError("This ticket is already checked in.")
    if ticket.booking_status is BookingStatus.CANCELLED:
        raise ConflictError("A cancelled ticket cannot be checked in.")

    flight = await session.get(Flight, ticket.flight_id)
    assert flight is not None  # FK guarantees this
    if flight.status not in BOOKABLE_STATUSES:
        raise ConflictError(
            f"Flight {flight.flight_number} is {flight.status.value}; check-in is closed.",
            details={"flight_status": flight.status.value},
        )

    ticket.booking_status = BookingStatus.CHECKED_IN
    ticket.checked_in_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(ticket)

    logger.info("passenger checked in", extra={"ticket_id": ticket.id})
    return ticket


async def cancel_ticket(session: AsyncSession, ticket_id: int) -> Ticket:
    ticket = await get_ticket(session, ticket_id)

    if ticket.booking_status is BookingStatus.CANCELLED:
        raise ConflictError("This ticket is already cancelled.")

    ticket.booking_status = BookingStatus.CANCELLED
    # Required by ck_tickets_checked_in_at_matches_status.
    ticket.checked_in_at = None
    await session.commit()
    await session.refresh(ticket)

    logger.info("ticket cancelled", extra={"ticket_id": ticket.id})
    return ticket

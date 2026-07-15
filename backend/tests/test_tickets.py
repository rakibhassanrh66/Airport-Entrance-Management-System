import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.errors import ConflictError, NotFoundError
from app.models.enums import BookingStatus, FlightStatus, TicketClass
from app.models.operations import Airline, Flight, Passenger, Ticket
from app.schemas.operations import TicketCreate
from app.services import tickets as ticket_service


def _booking(flight_id: int, passenger_id: int, seat: str = "12A") -> TicketCreate:
    return TicketCreate(
        flight_id=flight_id,
        passenger_id=passenger_id,
        seat_number=seat,
        ticket_class=TicketClass.ECONOMY,
        price=Decimal("450.00"),
    )


async def test_book_ticket_succeeds(session, flight, passenger):
    ticket = await ticket_service.book_ticket(session, _booking(flight.id, passenger.id))

    assert ticket.id is not None
    assert ticket.seat_number == "12A"
    assert ticket.booking_status is BookingStatus.CONFIRMED
    assert ticket.checked_in_at is None


async def test_seat_cannot_be_double_booked(session, flight, passenger, other_passenger):
    await ticket_service.book_ticket(session, _booking(flight.id, passenger.id, "12A"))

    with pytest.raises(ConflictError) as exc:
        await ticket_service.book_ticket(session, _booking(flight.id, other_passenger.id, "12A"))

    assert "already taken" in exc.value.message
    assert exc.value.details["seat_number"] == "12A"


async def test_cancelling_releases_the_seat_for_resale(session, flight, passenger, other_passenger):
    first = await ticket_service.book_ticket(session, _booking(flight.id, passenger.id, "12A"))
    await ticket_service.cancel_ticket(session, first.id)

    # The partial unique index only covers live bookings, so 12A is free again.
    resold = await ticket_service.book_ticket(
        session, _booking(flight.id, other_passenger.id, "12A")
    )
    assert resold.seat_number == "12A"
    assert resold.booking_status is BookingStatus.CONFIRMED


async def test_passenger_cannot_hold_two_live_tickets_on_one_flight(session, flight, passenger):
    await ticket_service.book_ticket(session, _booking(flight.id, passenger.id, "12A"))

    with pytest.raises(ConflictError) as exc:
        await ticket_service.book_ticket(session, _booking(flight.id, passenger.id, "14B"))

    assert "already holds a live ticket" in exc.value.message


async def test_booking_rejected_when_flight_is_full(session, flight, passenger):
    """The `flight` fixture has seat_capacity=3."""
    from app.models.operations import Passenger as P  # noqa: PLC0415

    for i in range(3):
        p = P(
            first_name=f"Filler{i}",
            last_name="Passenger",
            date_of_birth=datetime(1990, 1, 1).date(),
            passport_number=f"FILL{i:05d}",
            nationality="Bangladesh",
        )
        session.add(p)
        await session.commit()
        await session.refresh(p)
        await ticket_service.book_ticket(session, _booking(flight.id, p.id, f"1{i}A"))

    with pytest.raises(ConflictError) as exc:
        await ticket_service.book_ticket(session, _booking(flight.id, passenger.id, "20A"))

    assert "fully booked" in exc.value.message
    assert exc.value.details["seat_capacity"] == 3


async def test_cannot_book_on_cancelled_flight(session, flight, passenger):
    flight.status = FlightStatus.CANCELLED
    await session.commit()

    with pytest.raises(ConflictError) as exc:
        await ticket_service.book_ticket(session, _booking(flight.id, passenger.id))

    assert exc.value.details["flight_status"] == "cancelled"


async def test_cannot_book_on_departed_flight(session, flight, passenger):
    flight.status = FlightStatus.DEPARTED
    await session.commit()

    with pytest.raises(ConflictError):
        await ticket_service.book_ticket(session, _booking(flight.id, passenger.id))


async def test_booking_unknown_flight_is_404(session, passenger):
    with pytest.raises(NotFoundError):
        await ticket_service.book_ticket(session, _booking(999_999, passenger.id))


async def test_booking_unknown_passenger_is_404(session, flight):
    with pytest.raises(NotFoundError):
        await ticket_service.book_ticket(session, _booking(flight.id, 999_999))


# --------------------------------------------------------------------------- check-in


async def test_check_in_sets_timestamp_and_status(session, flight, passenger):
    ticket = await ticket_service.book_ticket(session, _booking(flight.id, passenger.id))
    checked = await ticket_service.check_in(session, ticket.id)

    assert checked.booking_status is BookingStatus.CHECKED_IN
    assert checked.checked_in_at is not None


async def test_cannot_check_in_twice(session, flight, passenger):
    ticket = await ticket_service.book_ticket(session, _booking(flight.id, passenger.id))
    await ticket_service.check_in(session, ticket.id)

    with pytest.raises(ConflictError):
        await ticket_service.check_in(session, ticket.id)


async def test_cannot_check_in_cancelled_ticket(session, flight, passenger):
    ticket = await ticket_service.book_ticket(session, _booking(flight.id, passenger.id))
    await ticket_service.cancel_ticket(session, ticket.id)

    with pytest.raises(ConflictError):
        await ticket_service.check_in(session, ticket.id)


async def test_cancelling_checked_in_ticket_clears_timestamp(session, flight, passenger):
    """ck_tickets_checked_in_at_matches_status would reject a stale timestamp."""
    ticket = await ticket_service.book_ticket(session, _booking(flight.id, passenger.id))
    await ticket_service.check_in(session, ticket.id)

    cancelled = await ticket_service.cancel_ticket(session, ticket.id)
    assert cancelled.booking_status is BookingStatus.CANCELLED
    assert cancelled.checked_in_at is None


async def test_cannot_cancel_twice(session, flight, passenger):
    ticket = await ticket_service.book_ticket(session, _booking(flight.id, passenger.id))
    await ticket_service.cancel_ticket(session, ticket.id)

    with pytest.raises(ConflictError):
        await ticket_service.cancel_ticket(session, ticket.id)


# --------------------------------------------------------------------------- seat map


async def test_seat_map_reflects_live_bookings_only(session, flight, passenger):
    from app.services import flights as flight_service  # noqa: PLC0415

    ticket = await ticket_service.book_ticket(session, _booking(flight.id, passenger.id, "12A"))

    before = await flight_service.seat_map(session, flight.id)
    assert before.booked_seats == ["12A"]
    assert before.seats_available == 2

    await ticket_service.cancel_ticket(session, ticket.id)

    after = await flight_service.seat_map(session, flight.id)
    assert after.booked_seats == []
    assert after.seats_available == 3


# --------------------------------------------------------------------------- concurrency


async def test_concurrent_bookings_cannot_both_take_the_same_seat(engine):
    """The real prize: two independent connections racing for one seat.

    This test deliberately does not use the transaction-rollback `session`
    fixture, because both callers must be on genuinely separate connections for
    the race to exist at all. It cleans up after itself instead.
    """
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with maker() as setup:
        airline = Airline(name="Race Air", iata_code="RC", country="Bangladesh")
        setup.add(airline)
        await setup.commit()
        await setup.refresh(airline)

        depart = datetime.now(UTC) + timedelta(days=30)
        flight = Flight(
            flight_number="RC900",
            airline_id=airline.id,
            source="DAC",
            destination="SIN",
            departure_time=depart,
            arrival_time=depart + timedelta(hours=4),
            seat_capacity=100,
        )
        setup.add(flight)

        people = [
            Passenger(
                first_name=f"Racer{i}",
                last_name="Concurrent",
                date_of_birth=datetime(1990, 1, 1).date(),
                passport_number=f"RACE{i:05d}",
                nationality="Bangladesh",
            )
            for i in range(2)
        ]
        setup.add_all(people)
        await setup.commit()
        await setup.refresh(flight)
        for p in people:
            await setup.refresh(p)

        flight_id = flight.id
        passenger_ids = [p.id for p in people]
        airline_id = airline.id

    async def attempt(passenger_id: int) -> str:
        async with maker() as s:
            try:
                await ticket_service.book_ticket(s, _booking(flight_id, passenger_id, "1A"))
                return "booked"
            except ConflictError:
                return "rejected"

    try:
        results = await asyncio.gather(*(attempt(pid) for pid in passenger_ids))

        # Exactly one wins. Never two: that would mean one seat, two passengers.
        assert sorted(results) == ["booked", "rejected"], results

        async with maker() as check:
            seats = (
                await check.scalars(
                    select(Ticket).where(
                        Ticket.flight_id == flight_id,
                        Ticket.seat_number == "1A",
                        Ticket.booking_status.in_(
                            [BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN]
                        ),
                    )
                )
            ).all()
            assert len(seats) == 1
    finally:
        async with maker() as cleanup:
            await cleanup.execute(delete(Ticket).where(Ticket.flight_id == flight_id))
            await cleanup.execute(delete(Flight).where(Flight.id == flight_id))
            await cleanup.execute(delete(Passenger).where(Passenger.id.in_(passenger_ids)))
            await cleanup.execute(delete(Airline).where(Airline.id == airline_id))
            await cleanup.commit()

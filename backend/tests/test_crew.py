"""Crew rostering, and the rule that a crew member cannot be in two places at once."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.errors import ConflictError, NotFoundError
from app.models.enums import CrewRole, FlightStatus
from app.models.operations import Airline, Employee, Flight, FlightCrewSchedule
from app.schemas.operations import CrewAssignmentCreate
from app.services import crew as crew_service


@pytest.fixture
async def employee(session):
    e = Employee(
        name="Captain Roy", role="pilot", department="flight-ops", salary=Decimal("120000.00")
    )
    session.add(e)
    await session.commit()
    await session.refresh(e)
    return e


@pytest.fixture
async def second_flight(session, airline):
    """A flight whose window overlaps the `flight` fixture's (both depart +7d)."""
    depart = datetime.now(UTC) + timedelta(days=7, hours=1)
    f = Flight(
        flight_number="BG900",
        airline_id=airline.id,
        source="DAC",
        destination="SIN",
        departure_time=depart,
        arrival_time=depart + timedelta(hours=5),
        seat_capacity=180,
    )
    session.add(f)
    await session.commit()
    await session.refresh(f)
    return f


def _assign(flight_id: int, crew_member_id: int) -> CrewAssignmentCreate:
    return CrewAssignmentCreate(
        flight_id=flight_id, crew_member_id=crew_member_id, role=CrewRole.PILOT
    )


async def test_assign_crew_copies_the_flight_window(session, flight, employee):
    a = await crew_service.assign_crew(session, _assign(flight.id, employee.id))
    assert a.starts_at == flight.departure_time
    assert a.ends_at == flight.arrival_time
    assert a.cancelled_at is None


async def test_same_crew_member_cannot_double_book_the_same_flight(session, flight, employee):
    await crew_service.assign_crew(session, _assign(flight.id, employee.id))
    with pytest.raises(ConflictError) as exc:
        await crew_service.assign_crew(session, _assign(flight.id, employee.id))
    assert "already assigned to this flight" in exc.value.message


async def test_crew_member_cannot_be_on_two_overlapping_flights(
    session, flight, second_flight, employee
):
    """The point of the whole exclusion constraint. Two different flights, but
    their windows overlap, so one person cannot crew both."""
    # Capture before the conflicting call: assign_crew rolls back on conflict,
    # which expires every object in this shared session — including `flight` —
    # so reading flight.id afterwards would trigger a sync lazy-load.
    first_flight_id = flight.id
    await crew_service.assign_crew(session, _assign(first_flight_id, employee.id))

    with pytest.raises(ConflictError) as exc:
        await crew_service.assign_crew(session, _assign(second_flight.id, employee.id))
    assert "overlapping flight" in exc.value.message
    assert exc.value.details["conflicting_flight_id"] == first_flight_id


async def test_crew_member_can_work_back_to_back_non_overlapping_flights(
    session, airline, employee, flight
):
    """tstzrange is half-open, so a flight that ends exactly when the next begins
    does not overlap — the crew member is free to work both."""
    later_depart = flight.arrival_time
    later = Flight(
        flight_number="BG901",
        airline_id=airline.id,
        source="DXB",
        destination="DAC",
        departure_time=later_depart,
        arrival_time=later_depart + timedelta(hours=6),
        seat_capacity=180,
    )
    session.add(later)
    await session.commit()
    await session.refresh(later)

    await crew_service.assign_crew(session, _assign(flight.id, employee.id))
    # Must not raise: [a, b) then [b, c) share only the boundary instant.
    await crew_service.assign_crew(session, _assign(later.id, employee.id))


async def test_releasing_frees_the_crew_member_to_be_rostered_again(
    session, flight, second_flight, employee
):
    a = await crew_service.assign_crew(session, _assign(flight.id, employee.id))
    await crew_service.release_crew(session, a.id)

    # The overlapping flight is now assignable, because the first assignment is
    # cancelled and both the partial unique index and the exclusion skip it.
    b = await crew_service.assign_crew(session, _assign(second_flight.id, employee.id))
    assert b.id is not None


async def test_cannot_crew_a_cancelled_flight(session, flight, employee):
    flight.status = FlightStatus.CANCELLED
    await session.commit()

    with pytest.raises(ConflictError):
        await crew_service.assign_crew(session, _assign(flight.id, employee.id))


async def test_assign_unknown_employee_is_404(session, flight):
    with pytest.raises(NotFoundError):
        await crew_service.assign_crew(session, _assign(flight.id, 999999))


async def test_double_release_is_rejected(session, flight, employee):
    a = await crew_service.assign_crew(session, _assign(flight.id, employee.id))
    await crew_service.release_crew(session, a.id)
    with pytest.raises(ConflictError):
        await crew_service.release_crew(session, a.id)


async def test_flight_roster_lists_live_assignments(session, flight, employee):
    await crew_service.assign_crew(session, _assign(flight.id, employee.id))
    roster = await crew_service.flight_roster(session, flight.id)
    assert [r.crew_member_id for r in roster] == [employee.id]


async def test_concurrent_rostering_cannot_double_book_a_crew_member(engine):
    """The same race as the seat demo, one axis over: two connections try to
    put one crew member on two overlapping flights at the same instant. The GiST
    exclusion constraint lets exactly one through.

    Uses raw connections, not the rollback `session` fixture, because the race
    only exists across genuinely separate transactions.
    """
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with maker() as setup:
        airline = Airline(name="Crew Air", iata_code="CW", country="Bangladesh")
        setup.add(airline)
        await setup.commit()
        await setup.refresh(airline)

        base = datetime.now(UTC) + timedelta(days=40)
        # Two flights whose windows overlap.
        flights = [
            Flight(
                flight_number=f"CW90{i}",
                airline_id=airline.id,
                source="DAC",
                destination="SIN",
                departure_time=base + timedelta(hours=i),
                arrival_time=base + timedelta(hours=i + 5),
                seat_capacity=100,
            )
            for i in range(2)
        ]
        setup.add_all(flights)
        employee = Employee(
            name="Race Pilot", role="pilot", department="flight-ops", salary=Decimal("100000.00")
        )
        setup.add(employee)
        await setup.commit()
        for f in flights:
            await setup.refresh(f)
        await setup.refresh(employee)

        flight_ids = [f.id for f in flights]
        employee_id = employee.id
        airline_id = airline.id

    async def attempt(flight_id: int) -> str:
        async with maker() as s:
            try:
                await crew_service.assign_crew(s, _assign(flight_id, employee_id))
                return "assigned"
            except ConflictError:
                return "rejected"

    try:
        results = await asyncio.gather(*(attempt(fid) for fid in flight_ids))
        assert sorted(results) == ["assigned", "rejected"], results

        async with maker() as check:
            live = (
                await check.scalars(
                    select(FlightCrewSchedule).where(
                        FlightCrewSchedule.crew_member_id == employee_id,
                        FlightCrewSchedule.cancelled_at.is_(None),
                    )
                )
            ).all()
            assert len(live) == 1
    finally:
        async with maker() as cleanup:
            await cleanup.execute(
                delete(FlightCrewSchedule).where(FlightCrewSchedule.crew_member_id == employee_id)
            )
            await cleanup.execute(delete(Flight).where(Flight.id.in_(flight_ids)))
            await cleanup.execute(delete(Employee).where(Employee.id == employee_id))
            await cleanup.execute(delete(Airline).where(Airline.id == airline_id))
            await cleanup.commit()

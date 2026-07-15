from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.errors import ConflictError, IllegalStateTransitionError, NotFoundError
from app.models.enums import BookingStatus, FlightStatus, TicketClass
from app.schemas.operations import FlightCreate, GateAssignmentCreate, TicketCreate
from app.services import flights as flight_service
from app.services import gates as gate_service
from app.services import tickets as ticket_service


async def test_create_flight(session, airline):
    depart = datetime.now(UTC) + timedelta(days=3)
    flight = await flight_service.create_flight(
        session,
        FlightCreate(
            flight_number="bg201",
            airline_id=airline.id,
            source="DAC",
            destination="LHR",
            departure_time=depart,
            arrival_time=depart + timedelta(hours=10),
        ),
    )
    assert flight.flight_number == "BG201"  # normalised to uppercase
    assert flight.status is FlightStatus.SCHEDULED


async def test_duplicate_flight_number_rejected(session, airline, flight):
    depart = datetime.now(UTC) + timedelta(days=3)
    with pytest.raises(ConflictError):
        await flight_service.create_flight(
            session,
            FlightCreate(
                flight_number="BG147",
                airline_id=airline.id,
                source="DAC",
                destination="LHR",
                departure_time=depart,
                arrival_time=depart + timedelta(hours=10),
            ),
        )


async def test_create_flight_unknown_airline(session):
    depart = datetime.now(UTC) + timedelta(days=3)
    with pytest.raises(NotFoundError):
        await flight_service.create_flight(
            session,
            FlightCreate(
                flight_number="ZZ999",
                airline_id=999_999,
                source="DAC",
                destination="LHR",
                departure_time=depart,
                arrival_time=depart + timedelta(hours=10),
            ),
        )


def test_schema_rejects_arrival_before_departure(airline_id: int = 1):
    depart = datetime.now(UTC) + timedelta(days=3)
    with pytest.raises(ValueError, match="arrival_time must be after departure_time"):
        FlightCreate(
            flight_number="ZZ100",
            airline_id=airline_id,
            source="DAC",
            destination="LHR",
            departure_time=depart,
            arrival_time=depart - timedelta(hours=1),
        )


def test_schema_rejects_same_source_and_destination():
    depart = datetime.now(UTC) + timedelta(days=3)
    with pytest.raises(ValueError, match="source and destination must differ"):
        FlightCreate(
            flight_number="ZZ100",
            airline_id=1,
            source="DAC",
            destination="dac",
            departure_time=depart,
            arrival_time=depart + timedelta(hours=1),
        )


# --------------------------------------------------------------------------- status machine


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (FlightStatus.SCHEDULED, FlightStatus.BOARDING),
        (FlightStatus.SCHEDULED, FlightStatus.DELAYED),
        (FlightStatus.SCHEDULED, FlightStatus.CANCELLED),
        (FlightStatus.DELAYED, FlightStatus.BOARDING),
        (FlightStatus.BOARDING, FlightStatus.DEPARTED),
        (FlightStatus.DEPARTED, FlightStatus.COMPLETED),
    ],
)
async def test_legal_transitions_are_accepted(session, flight, start, target):
    flight.status = start
    await session.commit()

    updated = await flight_service.change_status(session, flight.id, target)
    assert updated.status is target


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (FlightStatus.SCHEDULED, FlightStatus.DEPARTED),  # cannot skip boarding
        (FlightStatus.SCHEDULED, FlightStatus.COMPLETED),  # cannot skip the whole flight
        (FlightStatus.COMPLETED, FlightStatus.SCHEDULED),  # cannot un-complete
        (FlightStatus.CANCELLED, FlightStatus.BOARDING),  # cannot un-cancel
        (FlightStatus.DEPARTED, FlightStatus.CANCELLED),  # too late to cancel
        (FlightStatus.BOARDING, FlightStatus.SCHEDULED),  # cannot go backwards
    ],
)
async def test_illegal_transitions_are_rejected(session, flight, start, target):
    flight.status = start
    await session.commit()

    with pytest.raises(IllegalStateTransitionError) as exc:
        await flight_service.change_status(session, flight.id, target)

    assert exc.value.details["current"] == start.value
    assert exc.value.details["requested"] == target.value
    assert target.value not in exc.value.details["allowed"]


async def test_cancelling_flight_cancels_its_live_tickets(session, flight, passenger):
    ticket = await ticket_service.book_ticket(
        session,
        TicketCreate(
            flight_id=flight.id,
            passenger_id=passenger.id,
            seat_number="12A",
            ticket_class=TicketClass.ECONOMY,
            price=Decimal("450.00"),
        ),
    )
    assert ticket.booking_status is BookingStatus.CONFIRMED

    await flight_service.change_status(session, flight.id, FlightStatus.CANCELLED)

    await session.refresh(ticket)
    assert ticket.booking_status is BookingStatus.CANCELLED


async def test_cancelling_flight_releases_its_gate(session, flight, gate):
    starts = datetime.now(UTC) + timedelta(days=7)
    assignment = await gate_service.assign_gate(
        session,
        GateAssignmentCreate(
            gate_id=gate.id,
            flight_id=flight.id,
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
        ),
    )
    assert assignment.cancelled_at is None

    await flight_service.change_status(session, flight.id, FlightStatus.CANCELLED)

    await session.refresh(assignment)
    assert assignment.cancelled_at is not None


async def test_cancelling_flight_frees_the_gate_for_another_flight(session, flight, gate, airline):
    """The point of releasing gates: the slot must become reusable."""
    starts = datetime.now(UTC) + timedelta(days=7)
    window = {"starts_at": starts, "ends_at": starts + timedelta(hours=1)}

    # Read the ids up front. The expected ConflictError below rolls the session
    # back, which expires every loaded instance; touching flight.id afterwards
    # would trigger a lazy reload instead of returning the value.
    gate_id, flight_id = gate.id, flight.id

    await gate_service.assign_gate(
        session, GateAssignmentCreate(gate_id=gate_id, flight_id=flight_id, **window)
    )

    replacement = await flight_service.create_flight(
        session,
        FlightCreate(
            flight_number="BG148",
            airline_id=airline.id,
            source="DAC",
            destination="DXB",
            departure_time=starts,
            arrival_time=starts + timedelta(hours=6),
        ),
    )
    replacement_id = replacement.id

    # Blocked while the first flight holds the slot.
    with pytest.raises(ConflictError):
        await gate_service.assign_gate(
            session, GateAssignmentCreate(gate_id=gate_id, flight_id=replacement_id, **window)
        )

    await flight_service.change_status(session, flight_id, FlightStatus.CANCELLED)

    # Now the slot is free.
    ok = await gate_service.assign_gate(
        session, GateAssignmentCreate(gate_id=gate_id, flight_id=replacement_id, **window)
    )
    assert ok.id is not None


async def test_status_change_on_unknown_flight_is_404(session):
    with pytest.raises(NotFoundError):
        await flight_service.change_status(session, 999_999, FlightStatus.BOARDING)


# --------------------------------------------------------------------------- api surface


async def test_list_flights_filters_by_destination(client, admin_headers, flight):
    hit = await client.get("/api/v1/flights?destination=dxb", headers=admin_headers)
    assert hit.status_code == 200
    assert hit.json()["total"] == 1

    miss = await client.get("/api/v1/flights?destination=JFK", headers=admin_headers)
    assert miss.json()["total"] == 0


async def test_list_flights_destination_filter_is_not_sql_injectable(client, admin_headers, flight):
    """The PHP prototype concatenated this value straight into a query."""
    resp = await client.get(
        "/api/v1/flights", params={"destination": "DXB' OR '1'='1"}, headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0  # treated as a literal string, not SQL


async def test_flight_status_endpoint_rejects_illegal_transition(client, admin_headers, flight):
    resp = await client.patch(
        f"/api/v1/flights/{flight.id}/status",
        headers=admin_headers,
        json={"status": "completed"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "illegal_state_transition"


async def test_pagination_reports_total_independent_of_limit(
    client, admin_headers, session, airline
):
    depart = datetime.now(UTC) + timedelta(days=1)
    for i in range(5):
        await flight_service.create_flight(
            session,
            FlightCreate(
                flight_number=f"BG{300 + i}",
                airline_id=airline.id,
                source="DAC",
                destination="CGP",
                departure_time=depart + timedelta(hours=i),
                arrival_time=depart + timedelta(hours=i + 2),
            ),
        )

    resp = await client.get("/api/v1/flights?limit=2&destination=CGP", headers=admin_headers)
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5

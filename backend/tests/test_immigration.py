from decimal import Decimal

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.models.enums import ImmigrationStatus, TicketClass
from app.schemas.operations import ImmigrationCreate, ImmigrationDecision, TicketCreate
from app.services import immigration as immigration_service
from app.services import tickets as ticket_service
from tests.conftest import auth_headers


@pytest.fixture
async def ticket(session, flight, passenger):
    return await ticket_service.book_ticket(
        session,
        TicketCreate(
            flight_id=flight.id,
            passenger_id=passenger.id,
            seat_number="12A",
            ticket_class=TicketClass.ECONOMY,
            price=Decimal("450.00"),
        ),
    )


async def test_open_case_for_ticketed_passenger(session, ticket, flight, passenger):
    case = await immigration_service.open_case(
        session, ImmigrationCreate(passenger_id=passenger.id, flight_id=flight.id)
    )
    assert case.status is ImmigrationStatus.PENDING
    assert case.processed_at is None


async def test_cannot_open_case_without_a_ticket(session, flight, other_passenger):
    """The original schema allowed immigration rows for passengers never booked."""
    with pytest.raises(ConflictError) as exc:
        await immigration_service.open_case(
            session, ImmigrationCreate(passenger_id=other_passenger.id, flight_id=flight.id)
        )
    assert "no live ticket" in exc.value.message


async def test_cancelled_ticket_does_not_permit_a_case(session, ticket, flight, passenger):
    await ticket_service.cancel_ticket(session, ticket.id)

    with pytest.raises(ConflictError):
        await immigration_service.open_case(
            session, ImmigrationCreate(passenger_id=passenger.id, flight_id=flight.id)
        )


async def test_duplicate_case_rejected(session, ticket, flight, passenger):
    await immigration_service.open_case(
        session, ImmigrationCreate(passenger_id=passenger.id, flight_id=flight.id)
    )
    with pytest.raises(ConflictError) as exc:
        await immigration_service.open_case(
            session, ImmigrationCreate(passenger_id=passenger.id, flight_id=flight.id)
        )
    assert "already exists" in exc.value.message


async def test_open_case_unknown_passenger(session, flight):
    with pytest.raises(NotFoundError):
        await immigration_service.open_case(
            session, ImmigrationCreate(passenger_id=999_999, flight_id=flight.id)
        )


async def test_approve_case_sets_processed_at(session, ticket, flight, passenger):
    case = await immigration_service.open_case(
        session, ImmigrationCreate(passenger_id=passenger.id, flight_id=flight.id)
    )
    decided = await immigration_service.decide(
        session, case.id, ImmigrationDecision(status=ImmigrationStatus.APPROVED, remarks="Clear")
    )
    assert decided.status is ImmigrationStatus.APPROVED
    assert decided.processed_at is not None
    assert decided.remarks == "Clear"


async def test_case_cannot_be_decided_twice(session, ticket, flight, passenger):
    case = await immigration_service.open_case(
        session, ImmigrationCreate(passenger_id=passenger.id, flight_id=flight.id)
    )
    await immigration_service.decide(
        session, case.id, ImmigrationDecision(status=ImmigrationStatus.APPROVED)
    )

    with pytest.raises(ConflictError) as exc:
        await immigration_service.decide(
            session, case.id, ImmigrationDecision(status=ImmigrationStatus.REJECTED)
        )
    assert exc.value.details["current_status"] == "approved"


def test_decision_cannot_be_pending():
    with pytest.raises(ValueError, match="must be 'approved' or 'rejected'"):
        ImmigrationDecision(status=ImmigrationStatus.PENDING)


async def test_immigration_requires_security_role(client, session, ticket, flight, passenger):
    from app.models.enums import StaffRole  # noqa: PLC0415
    from app.schemas.auth import StaffUserCreate  # noqa: PLC0415
    from app.services.auth import create_staff_user  # noqa: PLC0415

    checkin = await create_staff_user(
        session,
        StaffUserCreate(
            email="desk@airport.example.com",
            full_name="Check-in Desk",
            password="correct-horse-battery-staple",
            role=StaffRole.CHECKIN,
        ),
    )

    resp = await client.post(
        "/api/v1/immigration",
        headers=auth_headers(checkin),
        json={"passenger_id": passenger.id, "flight_id": flight.id},
    )
    assert resp.status_code == 403


async def test_security_officer_can_decide(
    client, security_user, session, ticket, flight, passenger
):
    case = await immigration_service.open_case(
        session, ImmigrationCreate(passenger_id=passenger.id, flight_id=flight.id)
    )
    resp = await client.post(
        f"/api/v1/immigration/{case.id}/decision",
        headers=auth_headers(security_user),
        json={"status": "rejected", "remarks": "Invalid visa"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"

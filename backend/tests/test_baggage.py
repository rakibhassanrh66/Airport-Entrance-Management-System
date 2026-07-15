from decimal import Decimal

import pytest

from app.core.errors import ConflictError, IllegalStateTransitionError, NotFoundError
from app.models.enums import BaggageStatus, TicketClass
from app.schemas.operations import BaggageCreate, TicketCreate
from app.services import baggage as baggage_service
from app.services import tickets as ticket_service


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


async def test_check_in_baggage_issues_a_tag(session, ticket):
    bag = await baggage_service.check_in_baggage(
        session, BaggageCreate(ticket_id=ticket.id, weight_kg=Decimal("23.50"))
    )
    assert bag.status is BaggageStatus.CHECKED_IN
    assert bag.tag_number.startswith("BG")
    assert len(bag.tag_number) == 10


async def test_tags_are_unique_across_bags(session, ticket):
    first = await baggage_service.check_in_baggage(
        session, BaggageCreate(ticket_id=ticket.id, weight_kg=Decimal("20"))
    )
    second = await baggage_service.check_in_baggage(
        session, BaggageCreate(ticket_id=ticket.id, weight_kg=Decimal("18"))
    )
    assert first.tag_number != second.tag_number


async def test_cannot_check_baggage_against_cancelled_ticket(session, ticket):
    await ticket_service.cancel_ticket(session, ticket.id)

    with pytest.raises(ConflictError):
        await baggage_service.check_in_baggage(
            session, BaggageCreate(ticket_id=ticket.id, weight_kg=Decimal("20"))
        )


async def test_baggage_requires_a_real_ticket(session):
    with pytest.raises(NotFoundError):
        await baggage_service.check_in_baggage(
            session, BaggageCreate(ticket_id=999_999, weight_kg=Decimal("20"))
        )


def test_schema_rejects_overweight_bag():
    with pytest.raises(ValueError):
        BaggageCreate(ticket_id=1, weight_kg=Decimal("150"))


def test_schema_rejects_zero_weight():
    with pytest.raises(ValueError):
        BaggageCreate(ticket_id=1, weight_kg=Decimal("0"))


async def test_find_by_tag(session, ticket):
    bag = await baggage_service.check_in_baggage(
        session, BaggageCreate(ticket_id=ticket.id, weight_kg=Decimal("20"))
    )
    found = await baggage_service.find_by_tag(session, bag.tag_number.lower())
    assert found.id == bag.id


async def test_find_by_unknown_tag_is_404(session):
    with pytest.raises(NotFoundError):
        await baggage_service.find_by_tag(session, "BGZZZZZZZZ")


# --------------------------------------------------------------------------- lifecycle


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (BaggageStatus.CHECKED_IN, BaggageStatus.IN_TRANSIT),
        (BaggageStatus.CHECKED_IN, BaggageStatus.LOADED),
        (BaggageStatus.CHECKED_IN, BaggageStatus.LOST),
        (BaggageStatus.IN_TRANSIT, BaggageStatus.DELIVERED),
        (BaggageStatus.LOADED, BaggageStatus.DELIVERED),
        (BaggageStatus.LOST, BaggageStatus.DELIVERED),  # a found bag can still arrive
    ],
)
async def test_legal_baggage_transitions(session, ticket, start, target):
    bag = await baggage_service.check_in_baggage(
        session, BaggageCreate(ticket_id=ticket.id, weight_kg=Decimal("20"))
    )
    bag.status = start
    await session.commit()

    updated = await baggage_service.change_status(session, bag.id, target)
    assert updated.status is target


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (BaggageStatus.DELIVERED, BaggageStatus.IN_TRANSIT),  # delivered is terminal
        (BaggageStatus.DELIVERED, BaggageStatus.LOST),
        (BaggageStatus.CHECKED_IN, BaggageStatus.DELIVERED),  # cannot teleport
        (BaggageStatus.LOST, BaggageStatus.IN_TRANSIT),
    ],
)
async def test_illegal_baggage_transitions(session, ticket, start, target):
    bag = await baggage_service.check_in_baggage(
        session, BaggageCreate(ticket_id=ticket.id, weight_kg=Decimal("20"))
    )
    bag.status = start
    await session.commit()

    with pytest.raises(IllegalStateTransitionError):
        await baggage_service.change_status(session, bag.id, target)


async def test_baggage_status_endpoint(client, admin_headers, session, ticket):
    bag = await baggage_service.check_in_baggage(
        session, BaggageCreate(ticket_id=ticket.id, weight_kg=Decimal("20"))
    )
    resp = await client.patch(
        f"/api/v1/baggage/{bag.id}/status", headers=admin_headers, json={"status": "loaded"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "loaded"


async def test_baggage_status_endpoint_rejects_illegal_jump(client, admin_headers, session, ticket):
    bag = await baggage_service.check_in_baggage(
        session, BaggageCreate(ticket_id=ticket.id, weight_kg=Decimal("20"))
    )
    resp = await client.patch(
        f"/api/v1/baggage/{bag.id}/status", headers=admin_headers, json={"status": "delivered"}
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "illegal_state_transition"
    assert "checked_in" in resp.json()["details"]["current"]

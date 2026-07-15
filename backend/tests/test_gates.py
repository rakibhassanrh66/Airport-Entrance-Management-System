from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.models.enums import GateStatus
from app.schemas.operations import GateAssignmentCreate
from app.services import gates as gate_service

BASE = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)


def _window(gate_id: int, flight_id: int, start_h: float, end_h: float) -> GateAssignmentCreate:
    return GateAssignmentCreate(
        gate_id=gate_id,
        flight_id=flight_id,
        starts_at=BASE + timedelta(hours=start_h),
        ends_at=BASE + timedelta(hours=end_h),
    )


async def test_assign_gate_succeeds(session, gate, flight):
    assignment = await gate_service.assign_gate(session, _window(gate.id, flight.id, 0, 1))
    assert assignment.id is not None
    assert assignment.cancelled_at is None


@pytest.mark.parametrize(
    ("start_h", "end_h", "label"),
    [
        (0.5, 1.5, "starts inside the existing window"),
        (-0.5, 0.5, "ends inside the existing window"),
        (0.25, 0.75, "entirely inside the existing window"),
        (-0.5, 1.5, "entirely contains the existing window"),
        (0, 1, "exactly the existing window"),
    ],
)
async def test_overlapping_assignments_are_rejected(session, gate, flight, start_h, end_h, label):
    await gate_service.assign_gate(session, _window(gate.id, flight.id, 0, 1))

    with pytest.raises(ConflictError) as exc:
        await gate_service.assign_gate(session, _window(gate.id, flight.id, start_h, end_h))

    assert "already assigned" in exc.value.message, label
    assert exc.value.details["conflicting_assignment_id"] is not None


async def test_adjacent_assignments_are_allowed(session, gate, flight):
    """tstzrange is half-open, so 10:00-11:00 and 11:00-12:00 do not collide."""
    await gate_service.assign_gate(session, _window(gate.id, flight.id, 0, 1))
    later = await gate_service.assign_gate(session, _window(gate.id, flight.id, 1, 2))
    assert later.id is not None


async def test_same_window_on_a_different_gate_is_allowed(session, gate, flight, terminal):
    from app.models.operations import Gate  # noqa: PLC0415

    other = Gate(terminal_id=terminal.id, gate_number="A2")
    session.add(other)
    await session.commit()
    await session.refresh(other)

    await gate_service.assign_gate(session, _window(gate.id, flight.id, 0, 1))
    ok = await gate_service.assign_gate(session, _window(other.id, flight.id, 0, 1))
    assert ok.id is not None


async def test_released_assignment_frees_the_window(session, gate, flight):
    first = await gate_service.assign_gate(session, _window(gate.id, flight.id, 0, 1))
    await gate_service.release_gate(session, first.id)

    # The exclusion constraint is filtered on cancelled_at IS NULL.
    again = await gate_service.assign_gate(session, _window(gate.id, flight.id, 0, 1))
    assert again.id is not None


async def test_cannot_release_twice(session, gate, flight):
    assignment = await gate_service.assign_gate(session, _window(gate.id, flight.id, 0, 1))
    await gate_service.release_gate(session, assignment.id)

    with pytest.raises(ConflictError):
        await gate_service.release_gate(session, assignment.id)


async def test_cannot_assign_gate_under_maintenance(session, gate, flight):
    gate.status = GateStatus.MAINTENANCE
    await session.commit()

    with pytest.raises(ConflictError) as exc:
        await gate_service.assign_gate(session, _window(gate.id, flight.id, 0, 1))

    assert exc.value.details["gate_status"] == "maintenance"


async def test_cannot_assign_cancelled_flight_to_a_gate(session, gate, flight):
    from app.models.enums import FlightStatus  # noqa: PLC0415

    flight.status = FlightStatus.CANCELLED
    await session.commit()

    with pytest.raises(ConflictError):
        await gate_service.assign_gate(session, _window(gate.id, flight.id, 0, 1))


async def test_assign_unknown_gate_is_404(session, flight):
    with pytest.raises(NotFoundError):
        await gate_service.assign_gate(session, _window(999_999, flight.id, 0, 1))


async def test_assign_unknown_flight_is_404(session, gate):
    with pytest.raises(NotFoundError):
        await gate_service.assign_gate(session, _window(gate.id, 999_999, 0, 1))


def test_schema_rejects_backwards_window():
    with pytest.raises(ValueError, match="ends_at must be after starts_at"):
        GateAssignmentCreate(
            gate_id=1, flight_id=1, starts_at=BASE, ends_at=BASE - timedelta(hours=1)
        )


async def test_gate_schedule_hides_released_by_default(session, gate, flight):
    live = await gate_service.assign_gate(session, _window(gate.id, flight.id, 0, 1))
    released = await gate_service.assign_gate(session, _window(gate.id, flight.id, 2, 3))
    await gate_service.release_gate(session, released.id)

    default = await gate_service.gate_schedule(session, gate.id)
    assert [a.id for a in default] == [live.id]

    everything = await gate_service.gate_schedule(session, gate.id, include_released=True)
    assert {a.id for a in everything} == {live.id, released.id}


async def test_gate_assignment_endpoint_returns_409_on_overlap(client, admin_headers, gate, flight):
    payload = {
        "gate_id": gate.id,
        "flight_id": flight.id,
        "starts_at": BASE.isoformat(),
        "ends_at": (BASE + timedelta(hours=1)).isoformat(),
    }
    first = await client.post("/api/v1/gate-assignments", headers=admin_headers, json=payload)
    assert first.status_code == 201, first.text

    second = await client.post("/api/v1/gate-assignments", headers=admin_headers, json=payload)
    assert second.status_code == 409
    assert second.json()["code"] == "conflict"

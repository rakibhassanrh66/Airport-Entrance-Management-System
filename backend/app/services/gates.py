import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models.enums import FlightStatus, GateStatus
from app.models.operations import Flight, Gate, GateAssignment
from app.schemas.operations import GateAssignmentCreate

logger = logging.getLogger(__name__)


async def get_gate(session: AsyncSession, gate_id: int) -> Gate:
    gate = await session.get(Gate, gate_id)
    if gate is None:
        raise NotFoundError(f"Gate {gate_id} not found.")
    return gate


async def assign_gate(session: AsyncSession, payload: GateAssignmentCreate) -> GateAssignment:
    """Reserve a gate for a flight over a time window.

    The overlap check is not done in Python. Two simultaneous requests would
    both see a free gate and both insert; instead the GiST exclusion constraint
    on (gate_id, tstzrange(starts_at, ends_at)) makes the second insert fail,
    and we translate that failure into a 409.
    """
    gate = await get_gate(session, payload.gate_id)

    if gate.status is GateStatus.MAINTENANCE:
        raise ConflictError(
            f"Gate {gate.gate_number} is under maintenance.",
            details={"gate_status": gate.status.value},
        )

    # Read this now, while the instance is live. session.rollback() below expires
    # every loaded object, and touching an expired attribute afterwards triggers
    # a lazy reload -- which raises MissingGreenlet from inside the except block.
    gate_number = gate.gate_number

    flight = await session.get(Flight, payload.flight_id)
    if flight is None:
        raise NotFoundError(f"Flight {payload.flight_id} not found.")
    if flight.status in {FlightStatus.CANCELLED, FlightStatus.COMPLETED}:
        raise ConflictError(
            f"Flight {flight.flight_number} is {flight.status.value}; it cannot hold a gate.",
            details={"flight_status": flight.status.value},
        )

    assignment = GateAssignment(
        gate_id=payload.gate_id,
        flight_id=payload.flight_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    session.add(assignment)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "gate_assignments_no_overlap" in str(exc.orig):
            conflicting = await _find_conflict(session, payload)
            raise ConflictError(
                f"Gate {gate_number} is already assigned during that window.",
                details={
                    "conflicting_assignment_id": conflicting.id if conflicting else None,
                    "conflicting_flight_id": conflicting.flight_id if conflicting else None,
                },
            ) from exc
        raise

    await session.refresh(assignment)
    logger.info(
        "gate assigned",
        extra={
            "gate_assignment_id": assignment.id,
            "gate_id": assignment.gate_id,
            "flight_id": assignment.flight_id,
        },
    )
    return assignment


async def _find_conflict(
    session: AsyncSession, payload: GateAssignmentCreate
) -> GateAssignment | None:
    """Look up what actually clashed, purely to give the caller a useful 409."""
    return await session.scalar(
        select(GateAssignment).where(
            GateAssignment.gate_id == payload.gate_id,
            GateAssignment.cancelled_at.is_(None),
            GateAssignment.starts_at < payload.ends_at,
            GateAssignment.ends_at > payload.starts_at,
        )
    )


async def release_gate(session: AsyncSession, assignment_id: int) -> GateAssignment:
    assignment = await session.get(GateAssignment, assignment_id)
    if assignment is None:
        raise NotFoundError(f"Gate assignment {assignment_id} not found.")
    if assignment.cancelled_at is not None:
        raise ConflictError("This gate assignment is already released.")

    assignment.cancelled_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(assignment)

    logger.info("gate released", extra={"gate_assignment_id": assignment.id})
    return assignment


async def gate_schedule(
    session: AsyncSession, gate_id: int, *, include_released: bool = False
) -> list[GateAssignment]:
    await get_gate(session, gate_id)

    stmt = select(GateAssignment).where(GateAssignment.gate_id == gate_id)
    if not include_released:
        stmt = stmt.where(GateAssignment.cancelled_at.is_(None))

    result = await session.scalars(stmt.order_by(GateAssignment.starts_at))
    return list(result)

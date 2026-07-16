"""Crew rostering.

The one rule here worth a service of its own: a crew member cannot work two
flights at once. It is enforced by a GiST exclusion constraint on
(crew_member_id, tstzrange(starts_at, ends_at)) — the same mechanism as gate
overlap, one axis over — so it holds under two simultaneous rostering requests
that an application-level "is this person free?" check would both wave through.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models.enums import FlightStatus
from app.models.operations import Employee, Flight, FlightCrewSchedule
from app.schemas.operations import CrewAssignmentCreate

logger = logging.getLogger(__name__)


async def assign_crew(session: AsyncSession, payload: CrewAssignmentCreate) -> FlightCrewSchedule:
    employee = await session.get(Employee, payload.crew_member_id)
    if employee is None:
        raise NotFoundError(f"Employee {payload.crew_member_id} not found.")

    flight = await session.get(Flight, payload.flight_id)
    if flight is None:
        raise NotFoundError(f"Flight {payload.flight_id} not found.")
    if flight.status in {FlightStatus.CANCELLED, FlightStatus.COMPLETED}:
        raise ConflictError(
            f"Flight {flight.flight_number} is {flight.status.value}; it cannot be crewed.",
            details={"flight_status": flight.status.value},
        )

    # Read before the possible rollback below expires these instances; touching
    # an expired attribute afterwards triggers a lazy load and MissingGreenlet.
    employee_name = employee.name
    # The window is the flight's, copied onto the row so the exclusion constraint
    # has a range to compare. This is the denormalisation the model documents.
    starts_at = flight.departure_time
    ends_at = flight.arrival_time

    assignment = FlightCrewSchedule(
        crew_member_id=payload.crew_member_id,
        flight_id=payload.flight_id,
        role=payload.role,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    session.add(assignment)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        orig = str(exc.orig)
        if "flight_crew_no_overlap" in orig:
            clash = await _find_overlap(session, payload.crew_member_id, starts_at, ends_at)
            raise ConflictError(
                f"{employee_name} is already rostered on an overlapping flight.",
                details={
                    "conflicting_assignment_id": clash.id if clash else None,
                    "conflicting_flight_id": clash.flight_id if clash else None,
                },
            ) from exc
        if "uq_flight_crew_active" in orig:
            raise ConflictError(
                f"{employee_name} is already assigned to this flight.",
                details={"flight_id": payload.flight_id},
            ) from exc
        raise

    await session.refresh(assignment)
    logger.info(
        "crew assigned",
        extra={
            "crew_assignment_id": assignment.id,
            "crew_member_id": assignment.crew_member_id,
            "flight_id": assignment.flight_id,
        },
    )
    return assignment


async def _find_overlap(
    session: AsyncSession, crew_member_id: int, starts_at: datetime, ends_at: datetime
) -> FlightCrewSchedule | None:
    """Look up the live assignment that clashed, to make the 409 useful."""
    return await session.scalar(
        select(FlightCrewSchedule).where(
            FlightCrewSchedule.crew_member_id == crew_member_id,
            FlightCrewSchedule.cancelled_at.is_(None),
            FlightCrewSchedule.starts_at < ends_at,
            FlightCrewSchedule.ends_at > starts_at,
        )
    )


async def release_crew(session: AsyncSession, assignment_id: int) -> FlightCrewSchedule:
    assignment = await session.get(FlightCrewSchedule, assignment_id)
    if assignment is None:
        raise NotFoundError(f"Crew assignment {assignment_id} not found.")
    if assignment.cancelled_at is not None:
        raise ConflictError("This crew assignment is already released.")

    assignment.cancelled_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(assignment)

    logger.info("crew released", extra={"crew_assignment_id": assignment.id})
    return assignment


async def flight_roster(
    session: AsyncSession, flight_id: int, *, include_released: bool = False
) -> list[FlightCrewSchedule]:
    flight = await session.get(Flight, flight_id)
    if flight is None:
        raise NotFoundError(f"Flight {flight_id} not found.")

    stmt = select(FlightCrewSchedule).where(FlightCrewSchedule.flight_id == flight_id)
    if not include_released:
        stmt = stmt.where(FlightCrewSchedule.cancelled_at.is_(None))

    rows = await session.scalars(stmt.order_by(FlightCrewSchedule.role))
    return list(rows)

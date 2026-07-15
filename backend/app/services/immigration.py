import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models.enums import ACTIVE_BOOKING_STATUSES, ImmigrationStatus
from app.models.operations import Flight, Immigration, Passenger, Ticket
from app.schemas.operations import ImmigrationCreate, ImmigrationDecision

logger = logging.getLogger(__name__)


async def open_case(session: AsyncSession, payload: ImmigrationCreate) -> Immigration:
    """Open an immigration case for a passenger on a flight.

    The original schema let you file immigration for any (passenger, flight)
    pair, including passengers who were never booked on that flight. Requiring
    a live ticket closes that hole.
    """
    passenger = await session.get(Passenger, payload.passenger_id)
    if passenger is None:
        raise NotFoundError(f"Passenger {payload.passenger_id} not found.")

    flight = await session.get(Flight, payload.flight_id)
    if flight is None:
        raise NotFoundError(f"Flight {payload.flight_id} not found.")

    ticket = await session.scalar(
        select(Ticket.id).where(
            Ticket.flight_id == payload.flight_id,
            Ticket.passenger_id == payload.passenger_id,
            Ticket.booking_status.in_(ACTIVE_BOOKING_STATUSES),
        )
    )
    if ticket is None:
        raise ConflictError(
            "That passenger holds no live ticket on that flight.",
            details={"passenger_id": payload.passenger_id, "flight_id": payload.flight_id},
        )

    case = Immigration(
        passenger_id=payload.passenger_id,
        flight_id=payload.flight_id,
        status=ImmigrationStatus.PENDING,
    )
    session.add(case)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_immigration_passenger_id_flight_id" in str(exc.orig):
            raise ConflictError(
                "An immigration case already exists for that passenger on that flight."
            ) from exc
        raise

    await session.refresh(case)
    logger.info("immigration case opened", extra={"immigration_id": case.id})
    return case


async def get_case(session: AsyncSession, case_id: int) -> Immigration:
    case = await session.get(Immigration, case_id)
    if case is None:
        raise NotFoundError(f"Immigration case {case_id} not found.")
    return case


async def decide(session: AsyncSession, case_id: int, payload: ImmigrationDecision) -> Immigration:
    case = await get_case(session, case_id)

    if case.status is not ImmigrationStatus.PENDING:
        raise ConflictError(
            f"This case was already {case.status.value}.",
            details={"current_status": case.status.value},
        )

    case.status = payload.status
    case.remarks = payload.remarks
    # ck_immigration_processed_at_matches_status requires these move together.
    case.processed_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(case)

    logger.info(
        "immigration decided",
        extra={"immigration_id": case.id, "decision": payload.status.value},
    )
    return case

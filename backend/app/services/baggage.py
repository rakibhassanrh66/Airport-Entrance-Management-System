import logging
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, IllegalStateTransitionError, NotFoundError
from app.models.enums import BAGGAGE_STATUS_TRANSITIONS, BaggageStatus, BookingStatus
from app.models.operations import Baggage, Ticket
from app.schemas.operations import BaggageCreate

logger = logging.getLogger(__name__)

_TAG_ALPHABET = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O to avoid misreads off a label


def _generate_tag() -> str:
    return "BG" + "".join(secrets.choice(_TAG_ALPHABET) for _ in range(8))


async def check_in_baggage(session: AsyncSession, payload: BaggageCreate) -> Baggage:
    """Accept a bag against a ticket.

    Hanging baggage off the ticket (rather than off passenger+flight as the
    original schema did) means a bag can only exist for a real booking.
    """
    ticket = await session.get(Ticket, payload.ticket_id)
    if ticket is None:
        raise NotFoundError(f"Ticket {payload.ticket_id} not found.")

    if ticket.booking_status is BookingStatus.CANCELLED:
        raise ConflictError("Cannot check baggage against a cancelled ticket.")

    bag = Baggage(
        ticket_id=payload.ticket_id,
        weight_kg=payload.weight_kg,
        tag_number=_generate_tag(),
        status=BaggageStatus.CHECKED_IN,
    )
    session.add(bag)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # A tag collision is a 1-in-34^8 event; retrying once is cheaper than
        # failing the passenger's check-in.
        if "tag_number" in str(exc.orig):
            bag = Baggage(
                ticket_id=payload.ticket_id,
                weight_kg=payload.weight_kg,
                tag_number=_generate_tag(),
                status=BaggageStatus.CHECKED_IN,
            )
            session.add(bag)
            await session.commit()
        else:
            raise

    await session.refresh(bag)
    logger.info(
        "baggage checked in",
        extra={"baggage_id": bag.id, "tag_number": bag.tag_number, "ticket_id": bag.ticket_id},
    )
    return bag


async def get_baggage(session: AsyncSession, baggage_id: int) -> Baggage:
    bag = await session.get(Baggage, baggage_id)
    if bag is None:
        raise NotFoundError(f"Baggage {baggage_id} not found.")
    return bag


async def find_by_tag(session: AsyncSession, tag_number: str) -> Baggage:
    bag = await session.scalar(select(Baggage).where(Baggage.tag_number == tag_number.upper()))
    if bag is None:
        raise NotFoundError(f"No baggage with tag {tag_number!r}.")
    return bag


async def change_status(
    session: AsyncSession, baggage_id: int, new_status: BaggageStatus
) -> Baggage:
    bag = await get_baggage(session, baggage_id)
    current = bag.status

    allowed = BAGGAGE_STATUS_TRANSITIONS[current]
    if new_status not in allowed:
        raise IllegalStateTransitionError(
            entity=f"baggage {bag.tag_number}",
            current=current.value,
            requested=new_status.value,
            allowed=sorted(s.value for s in allowed),
        )

    bag.status = new_status
    await session.commit()
    await session.refresh(bag)

    logger.info(
        "baggage status changed",
        extra={"baggage_id": bag.id, "from": current.value, "to": new_status.value},
    )
    return bag

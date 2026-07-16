"""Cargo lifecycle.

Runways and checkpoints carry a plain status the router sets directly; cargo has
an actual lifecycle (loaded → in transit → unloaded) worth guarding, so its
transitions go through the same state-machine check baggage uses.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import IllegalStateTransitionError, NotFoundError
from app.models.enums import CARGO_STATUS_TRANSITIONS, CargoStatus
from app.models.operations import Cargo

logger = logging.getLogger(__name__)


async def change_cargo_status(
    session: AsyncSession, cargo_id: int, new_status: CargoStatus
) -> Cargo:
    cargo = await session.get(Cargo, cargo_id)
    if cargo is None:
        raise NotFoundError(f"Cargo {cargo_id} not found.")

    current = cargo.status
    allowed = CARGO_STATUS_TRANSITIONS[current]
    if new_status not in allowed:
        raise IllegalStateTransitionError(
            entity=f"cargo {cargo.id}",
            current=current.value,
            requested=new_status.value,
            allowed=sorted(s.value for s in allowed),
        )

    cargo.status = new_status
    await session.commit()
    await session.refresh(cargo)

    logger.info(
        "cargo status changed",
        extra={"cargo_id": cargo.id, "from": current.value, "to": new_status.value},
    )
    return cargo

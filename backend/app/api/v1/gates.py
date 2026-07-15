from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, RequireOps, SessionDep
from app.api.v1._pagination import paginate
from app.core.errors import ConflictError, NotFoundError
from app.models.operations import Gate, Terminal
from app.schemas.common import Page
from app.schemas.operations import (
    GateAssignmentCreate,
    GateAssignmentOut,
    GateCreate,
    GateOut,
    TerminalCreate,
    TerminalOut,
)
from app.services import gates as gate_service

router = APIRouter(tags=["gates"])


# --------------------------------------------------------------------------- terminals


@router.get("/terminals", response_model=Page[TerminalOut], summary="List terminals")
async def list_terminals(
    session: SessionDep,
    _: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TerminalOut]:
    return await paginate(
        session,
        select(Terminal),
        schema=TerminalOut,
        limit=limit,
        offset=offset,
        order_by=Terminal.name,
    )


@router.post(
    "/terminals",
    response_model=TerminalOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a terminal",
)
async def create_terminal(
    payload: TerminalCreate, session: SessionDep, _: RequireOps
) -> TerminalOut:
    terminal = Terminal(**payload.model_dump())
    session.add(terminal)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(f"Terminal {payload.name!r} already exists.") from exc

    await session.refresh(terminal)
    return TerminalOut.model_validate(terminal)


# --------------------------------------------------------------------------- gates


@router.get("/gates", response_model=Page[GateOut], summary="List gates")
async def list_gates(
    session: SessionDep,
    _: CurrentUser,
    terminal_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[GateOut]:
    stmt = select(Gate)
    if terminal_id is not None:
        stmt = stmt.where(Gate.terminal_id == terminal_id)
    return await paginate(
        session, stmt, schema=GateOut, limit=limit, offset=offset, order_by=Gate.gate_number
    )


@router.post(
    "/gates", response_model=GateOut, status_code=status.HTTP_201_CREATED, summary="Add a gate"
)
async def create_gate(payload: GateCreate, session: SessionDep, _: RequireOps) -> GateOut:
    terminal = await session.get(Terminal, payload.terminal_id)
    if terminal is None:
        raise NotFoundError(f"Terminal {payload.terminal_id} not found.")

    gate = Gate(**payload.model_dump())
    session.add(gate)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            f"Gate {payload.gate_number!r} already exists in that terminal."
        ) from exc

    await session.refresh(gate)
    return GateOut.model_validate(gate)


@router.get(
    "/gates/{gate_id}/schedule",
    response_model=list[GateAssignmentOut],
    summary="What is scheduled at this gate",
)
async def gate_schedule(
    gate_id: int,
    session: SessionDep,
    _: CurrentUser,
    include_released: Annotated[bool, Query()] = False,
) -> list[GateAssignmentOut]:
    rows = await gate_service.gate_schedule(session, gate_id, include_released=include_released)
    return [GateAssignmentOut.model_validate(r) for r in rows]


# --------------------------------------------------------------------------- assignments


@router.post(
    "/gate-assignments",
    response_model=GateAssignmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Reserve a gate for a flight",
    description=(
        "Returns 409 if the gate is already reserved for any overlapping window. "
        "Enforced by a PostgreSQL exclusion constraint, so it holds under concurrency."
    ),
)
async def assign_gate(
    payload: GateAssignmentCreate, session: SessionDep, _: RequireOps
) -> GateAssignmentOut:
    assignment = await gate_service.assign_gate(session, payload)
    return GateAssignmentOut.model_validate(assignment)


@router.post(
    "/gate-assignments/{assignment_id}/release",
    response_model=GateAssignmentOut,
    summary="Release a gate reservation",
)
async def release_gate(assignment_id: int, session: SessionDep, _: RequireOps) -> GateAssignmentOut:
    assignment = await gate_service.release_gate(session, assignment_id)
    return GateAssignmentOut.model_validate(assignment)

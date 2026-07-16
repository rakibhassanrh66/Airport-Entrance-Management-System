"""Runways and cargo — the airside operational resources."""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, RequireOps, SessionDep
from app.api.v1._pagination import paginate
from app.core.errors import ConflictError, NotFoundError
from app.models.operations import Cargo, Flight, Runway
from app.schemas.common import Page
from app.schemas.operations import (
    CargoCreate,
    CargoOut,
    CargoStatusUpdate,
    RunwayCreate,
    RunwayOut,
    RunwayStatusUpdate,
)
from app.services import airside as airside_service

router = APIRouter()


# --------------------------------------------------------------------------- runways


@router.get("/runways", response_model=Page[RunwayOut], summary="List runways", tags=["runways"])
async def list_runways(
    session: SessionDep,
    _: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RunwayOut]:
    return await paginate(
        session,
        select(Runway),
        schema=RunwayOut,
        limit=limit,
        offset=offset,
        order_by=Runway.runway_number,
    )


@router.post(
    "/runways",
    response_model=RunwayOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a runway",
    tags=["runways"],
)
async def create_runway(payload: RunwayCreate, session: SessionDep, _: RequireOps) -> RunwayOut:
    runway = Runway(**payload.model_dump())
    session.add(runway)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(f"Runway {payload.runway_number!r} already exists.") from exc
    await session.refresh(runway)
    return RunwayOut.model_validate(runway)


@router.patch(
    "/runways/{runway_id}/status",
    response_model=RunwayOut,
    summary="Set a runway's status",
    tags=["runways"],
)
async def set_runway_status(
    runway_id: int, payload: RunwayStatusUpdate, session: SessionDep, _: RequireOps
) -> RunwayOut:
    runway = await session.get(Runway, runway_id)
    if runway is None:
        raise NotFoundError(f"Runway {runway_id} not found.")
    runway.status = payload.status
    await session.commit()
    await session.refresh(runway)
    return RunwayOut.model_validate(runway)


# --------------------------------------------------------------------------- cargo


@router.get("/cargo", response_model=Page[CargoOut], summary="List cargo", tags=["cargo"])
async def list_cargo(
    session: SessionDep,
    _: CurrentUser,
    flight_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[CargoOut]:
    stmt = select(Cargo)
    if flight_id is not None:
        stmt = stmt.where(Cargo.flight_id == flight_id)
    return await paginate(
        session, stmt, schema=CargoOut, limit=limit, offset=offset, order_by=Cargo.id
    )


@router.post(
    "/cargo",
    response_model=CargoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a cargo consignment",
    tags=["cargo"],
)
async def create_cargo(payload: CargoCreate, session: SessionDep, _: RequireOps) -> CargoOut:
    if await session.get(Flight, payload.flight_id) is None:
        raise NotFoundError(f"Flight {payload.flight_id} not found.")
    cargo = Cargo(**payload.model_dump())
    session.add(cargo)
    await session.commit()
    await session.refresh(cargo)
    return CargoOut.model_validate(cargo)


@router.get(
    "/cargo/{cargo_id}", response_model=CargoOut, summary="Fetch one consignment", tags=["cargo"]
)
async def get_cargo(cargo_id: int, session: SessionDep, _: CurrentUser) -> CargoOut:
    cargo = await session.get(Cargo, cargo_id)
    if cargo is None:
        raise NotFoundError(f"Cargo {cargo_id} not found.")
    return CargoOut.model_validate(cargo)


@router.patch(
    "/cargo/{cargo_id}/status",
    response_model=CargoOut,
    summary="Move a consignment through its lifecycle",
    tags=["cargo"],
)
async def set_cargo_status(
    cargo_id: int, payload: CargoStatusUpdate, session: SessionDep, _: RequireOps
) -> CargoOut:
    cargo = await airside_service.change_cargo_status(session, cargo_id, payload.status)
    return CargoOut.model_validate(cargo)

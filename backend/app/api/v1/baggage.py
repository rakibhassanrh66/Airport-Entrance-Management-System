from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, RequireCheckin, SessionDep
from app.api.v1._pagination import paginate
from app.models.enums import BaggageStatus
from app.models.operations import Baggage
from app.schemas.common import Page
from app.schemas.operations import BaggageCreate, BaggageOut, BaggageStatusUpdate
from app.services import baggage as baggage_service

router = APIRouter(prefix="/baggage", tags=["baggage"])


@router.get("", response_model=Page[BaggageOut], summary="List baggage")
async def list_baggage(
    session: SessionDep,
    _: CurrentUser,
    ticket_id: Annotated[int | None, Query()] = None,
    status_filter: Annotated[BaggageStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[BaggageOut]:
    stmt = select(Baggage)
    if ticket_id is not None:
        stmt = stmt.where(Baggage.ticket_id == ticket_id)
    if status_filter is not None:
        stmt = stmt.where(Baggage.status == status_filter)
    return await paginate(
        session, stmt, schema=BaggageOut, limit=limit, offset=offset, order_by=Baggage.id
    )


@router.post(
    "",
    response_model=BaggageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Check a bag in against a ticket",
)
async def check_in_baggage(
    payload: BaggageCreate, session: SessionDep, _: RequireCheckin
) -> BaggageOut:
    bag = await baggage_service.check_in_baggage(session, payload)
    return BaggageOut.model_validate(bag)


@router.get("/by-tag/{tag_number}", response_model=BaggageOut, summary="Trace a bag by its tag")
async def find_by_tag(tag_number: str, session: SessionDep, _: CurrentUser) -> BaggageOut:
    bag = await baggage_service.find_by_tag(session, tag_number)
    return BaggageOut.model_validate(bag)


@router.patch(
    "/{baggage_id}/status",
    response_model=BaggageOut,
    summary="Move a bag through its lifecycle",
)
async def change_status(
    baggage_id: int, payload: BaggageStatusUpdate, session: SessionDep, _: RequireCheckin
) -> BaggageOut:
    bag = await baggage_service.change_status(session, baggage_id, payload.status)
    return BaggageOut.model_validate(bag)

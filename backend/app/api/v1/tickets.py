from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, RequireCheckin, SessionDep
from app.api.v1._pagination import paginate
from app.models.enums import BookingStatus
from app.models.operations import Ticket
from app.schemas.common import Page
from app.schemas.operations import TicketCreate, TicketOut
from app.services import tickets as ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=Page[TicketOut], summary="List tickets")
async def list_tickets(
    session: SessionDep,
    _: CurrentUser,
    flight_id: Annotated[int | None, Query()] = None,
    passenger_id: Annotated[int | None, Query()] = None,
    booking_status: Annotated[BookingStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TicketOut]:
    stmt = select(Ticket)
    if flight_id is not None:
        stmt = stmt.where(Ticket.flight_id == flight_id)
    if passenger_id is not None:
        stmt = stmt.where(Ticket.passenger_id == passenger_id)
    if booking_status is not None:
        stmt = stmt.where(Ticket.booking_status == booking_status)

    return await paginate(
        session, stmt, schema=TicketOut, limit=limit, offset=offset, order_by=Ticket.id
    )


@router.post(
    "",
    response_model=TicketOut,
    status_code=status.HTTP_201_CREATED,
    summary="Book a seat",
    description=(
        "Rejects a seat already held on the flight, a passenger who already holds a "
        "live ticket, a full flight, and any flight not open for booking."
    ),
)
async def book(payload: TicketCreate, session: SessionDep, _: RequireCheckin) -> TicketOut:
    ticket = await ticket_service.book_ticket(session, payload)
    return TicketOut.model_validate(ticket)


@router.get("/{ticket_id}", response_model=TicketOut, summary="Fetch one ticket")
async def get_ticket(ticket_id: int, session: SessionDep, _: CurrentUser) -> TicketOut:
    ticket = await ticket_service.get_ticket(session, ticket_id)
    return TicketOut.model_validate(ticket)


@router.post("/{ticket_id}/check-in", response_model=TicketOut, summary="Check a passenger in")
async def check_in(ticket_id: int, session: SessionDep, _: RequireCheckin) -> TicketOut:
    ticket = await ticket_service.check_in(session, ticket_id)
    return TicketOut.model_validate(ticket)


@router.post("/{ticket_id}/cancel", response_model=TicketOut, summary="Cancel a ticket")
async def cancel(ticket_id: int, session: SessionDep, _: RequireCheckin) -> TicketOut:
    ticket = await ticket_service.cancel_ticket(session, ticket_id)
    return TicketOut.model_validate(ticket)

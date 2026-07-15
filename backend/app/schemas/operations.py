"""Request/response schemas for the operational resources."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import (
    BaggageStatus,
    BookingStatus,
    FlightStatus,
    GateStatus,
    ImmigrationStatus,
    TicketClass,
)
from app.schemas.common import ORMModel

# --------------------------------------------------------------------------- airlines


class AirlineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    iata_code: str = Field(min_length=2, max_length=3)
    country: str = Field(min_length=1, max_length=100)
    contact_info: str | None = Field(default=None, max_length=255)

    @field_validator("iata_code")
    @classmethod
    def _upper(cls, v: str) -> str:
        # Normalise here so the DB's uppercase CHECK never fires on a request
        # that was merely lowercase rather than genuinely invalid.
        if not v.isalnum():
            raise ValueError("iata_code must be alphanumeric")
        return v.upper()


class AirlineOut(ORMModel):
    id: int
    name: str
    iata_code: str
    country: str
    contact_info: str | None


# --------------------------------------------------------------------------- flights


class FlightCreate(BaseModel):
    flight_number: str = Field(min_length=2, max_length=10)
    airline_id: int
    source: str = Field(min_length=1, max_length=100)
    destination: str = Field(min_length=1, max_length=100)
    departure_time: datetime
    arrival_time: datetime
    seat_capacity: int = Field(default=180, gt=0, le=1000)

    @field_validator("flight_number")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _check_times(self) -> "FlightCreate":
        if self.arrival_time <= self.departure_time:
            raise ValueError("arrival_time must be after departure_time")
        if self.source.strip().lower() == self.destination.strip().lower():
            raise ValueError("source and destination must differ")
        return self


class FlightStatusUpdate(BaseModel):
    status: FlightStatus


class FlightOut(ORMModel):
    id: int
    flight_number: str
    airline_id: int
    source: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    status: FlightStatus
    seat_capacity: int


class FlightSeatMap(BaseModel):
    flight_id: int
    seat_capacity: int
    booked_seats: list[str]
    seats_available: int


# --------------------------------------------------------------------------- passengers


class PassengerCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    date_of_birth: date
    passport_number: str = Field(min_length=5, max_length=20)
    nationality: str = Field(min_length=1, max_length=50)
    contact_info: str | None = Field(default=None, max_length=255)

    @field_validator("date_of_birth")
    @classmethod
    def _in_past(cls, v: date) -> date:
        if v >= date.today():
            raise ValueError("date_of_birth must be in the past")
        return v

    @field_validator("passport_number")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper().strip()


class PassengerOut(ORMModel):
    id: int
    first_name: str
    last_name: str
    date_of_birth: date
    passport_number: str
    nationality: str
    contact_info: str | None


# --------------------------------------------------------------------------- tickets


class TicketCreate(BaseModel):
    flight_id: int
    passenger_id: int
    seat_number: str = Field(min_length=2, max_length=5)
    ticket_class: TicketClass
    price: Decimal = Field(ge=0, decimal_places=2)

    @field_validator("seat_number")
    @classmethod
    def _normalise_seat(cls, v: str) -> str:
        seat = v.upper().strip()
        if not seat[:-1].isdigit() or not seat[-1].isalpha():
            raise ValueError("seat_number must look like '12A': digits then a letter")
        return seat


class TicketOut(ORMModel):
    id: int
    flight_id: int
    passenger_id: int
    seat_number: str
    ticket_class: TicketClass
    booking_status: BookingStatus
    price: Decimal
    checked_in_at: datetime | None


# --------------------------------------------------------------------------- terminals & gates


class TerminalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    capacity: int = Field(gt=0)


class TerminalOut(ORMModel):
    id: int
    name: str
    capacity: int


class GateCreate(BaseModel):
    terminal_id: int
    gate_number: str = Field(min_length=1, max_length=10)


class GateOut(ORMModel):
    id: int
    terminal_id: int
    gate_number: str
    status: GateStatus


class GateAssignmentCreate(BaseModel):
    gate_id: int
    flight_id: int
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def _check_window(self) -> "GateAssignmentCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class GateAssignmentOut(ORMModel):
    id: int
    gate_id: int
    flight_id: int
    starts_at: datetime
    ends_at: datetime
    cancelled_at: datetime | None


# --------------------------------------------------------------------------- baggage


class BaggageCreate(BaseModel):
    ticket_id: int
    weight_kg: Decimal = Field(gt=0, le=100, decimal_places=2)


class BaggageStatusUpdate(BaseModel):
    status: BaggageStatus


class BaggageOut(ORMModel):
    id: int
    ticket_id: int
    tag_number: str
    weight_kg: Decimal
    status: BaggageStatus


# --------------------------------------------------------------------------- immigration


class ImmigrationCreate(BaseModel):
    passenger_id: int
    flight_id: int


class ImmigrationDecision(BaseModel):
    status: ImmigrationStatus
    remarks: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def _must_be_terminal(cls, v: ImmigrationStatus) -> ImmigrationStatus:
        if v is ImmigrationStatus.PENDING:
            raise ValueError("a decision must be 'approved' or 'rejected'")
        return v


class ImmigrationOut(ORMModel):
    id: int
    passenger_id: int
    flight_id: int
    status: ImmigrationStatus
    remarks: str | None
    processed_at: datetime | None

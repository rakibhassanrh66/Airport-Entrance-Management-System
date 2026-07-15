"""Core operational domain: airlines, flights, ticketing, gates, baggage, immigration.

Ported from Devfiles/WEB and SQL/Main_databse.sql, with the defects of that
script corrected: database-generated identity keys instead of client-supplied
integers, real CHECK constraints, indexes on every foreign key and lookup
column, and the foreign key the original omitted on crew scheduling.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models._types import enum_type
from app.models.enums import (
    BaggageStatus,
    BookingStatus,
    CargoStatus,
    CheckpointStatus,
    CrewRole,
    FlightStatus,
    GateStatus,
    ImmigrationStatus,
    MaintenanceType,
    RunwayStatus,
    StaffRole,
    TerminalStatus,
    TicketClass,
)

if TYPE_CHECKING:
    from app.models.ancillary import EmergencyContact


class StaffUser(Base, TimestampMixin):
    """An authenticated operator of this API.

    Distinct from `Employee`, which is an HR record. A person may exist as an
    employee without ever holding a login, which is why these are separate.
    """

    __tablename__ = "staff_users"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[StaffRole] = mapped_column(enum_type(StaffRole), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    employee: Mapped["Employee | None"] = relationship(back_populates="staff_user")

    __table_args__ = (CheckConstraint("position('@' in email) > 1", name="email_has_at_sign"),)


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    contact_info: Mapped[str | None] = mapped_column(String(255))
    salary: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    staff_user: Mapped["StaffUser | None"] = relationship(back_populates="employee")
    maintenance_tasks: Mapped[list["MaintenanceSchedule"]] = relationship(back_populates="employee")
    crew_assignments: Mapped[list["FlightCrewSchedule"]] = relationship(
        back_populates="crew_member"
    )

    __table_args__ = (CheckConstraint("salary >= 0", name="salary_non_negative"),)


class Airline(Base, TimestampMixin):
    __tablename__ = "airlines"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    iata_code: Mapped[str] = mapped_column(String(3), nullable=False, unique=True, index=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_info: Mapped[str | None] = mapped_column(String(255))

    flights: Mapped[list["Flight"]] = relationship(back_populates="airline")
    staff: Mapped[list["AirlineStaff"]] = relationship(back_populates="airline")

    __table_args__ = (
        CheckConstraint("iata_code = upper(iata_code)", name="iata_code_uppercase"),
        CheckConstraint("char_length(iata_code) BETWEEN 2 AND 3", name="iata_code_length"),
    )


class Flight(Base, TimestampMixin):
    __tablename__ = "flights"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    flight_number: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)
    airline_id: Mapped[int] = mapped_column(
        ForeignKey("airlines.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    destination: Mapped[str] = mapped_column(String(100), nullable=False)
    departure_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[FlightStatus] = mapped_column(
        enum_type(FlightStatus),
        nullable=False,
        server_default=FlightStatus.SCHEDULED.value,
        index=True,
    )
    seat_capacity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="180")

    airline: Mapped["Airline"] = relationship(back_populates="flights")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="flight")
    gate_assignments: Mapped[list["GateAssignment"]] = relationship(back_populates="flight")
    cargo: Mapped[list["Cargo"]] = relationship(back_populates="flight")
    crew: Mapped[list["FlightCrewSchedule"]] = relationship(back_populates="flight")

    __table_args__ = (
        CheckConstraint("arrival_time > departure_time", name="arrival_after_departure"),
        CheckConstraint("source <> destination", name="source_differs_from_destination"),
        CheckConstraint("seat_capacity > 0", name="seat_capacity_positive"),
        Index("ix_flights_status_departure_time", "status", "departure_time"),
    )


class Passenger(Base, TimestampMixin):
    __tablename__ = "passengers"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    passport_number: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, index=True
    )
    nationality: Mapped[str] = mapped_column(String(50), nullable=False)
    contact_info: Mapped[str | None] = mapped_column(String(255))

    tickets: Mapped[list["Ticket"]] = relationship(back_populates="passenger")
    immigration_records: Mapped[list["Immigration"]] = relationship(back_populates="passenger")
    emergency_contacts: Mapped[list["EmergencyContact"]] = relationship(back_populates="passenger")

    __table_args__ = (
        CheckConstraint("date_of_birth < CURRENT_DATE", name="date_of_birth_in_past"),
    )


class Ticket(Base, TimestampMixin):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    flight_id: Mapped[int] = mapped_column(
        ForeignKey("flights.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    passenger_id: Mapped[int] = mapped_column(
        ForeignKey("passengers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    seat_number: Mapped[str] = mapped_column(String(5), nullable=False)
    ticket_class: Mapped[TicketClass] = mapped_column(enum_type(TicketClass), nullable=False)
    booking_status: Mapped[BookingStatus] = mapped_column(
        enum_type(BookingStatus),
        nullable=False,
        server_default=BookingStatus.CONFIRMED.value,
        index=True,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    flight: Mapped["Flight"] = relationship(back_populates="tickets")
    passenger: Mapped["Passenger"] = relationship(back_populates="tickets")
    baggage: Mapped[list["Baggage"]] = relationship(back_populates="ticket")

    __table_args__ = (
        # The seat rule the original schema had no way to express: a seat may be
        # held by at most one live booking per flight. Cancelled tickets are
        # excluded so a released seat can be resold. Enforced here rather than in
        # Python because two concurrent bookings would both pass an app-level check.
        Index(
            "uq_tickets_flight_seat_active",
            "flight_id",
            "seat_number",
            unique=True,
            postgresql_where=text("booking_status IN ('confirmed', 'checked_in')"),
        ),
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint("seat_number = upper(seat_number)", name="seat_number_uppercase"),
        CheckConstraint(
            "(booking_status = 'checked_in') = (checked_in_at IS NOT NULL)",
            name="checked_in_at_matches_status",
        ),
    )


class Terminal(Base, TimestampMixin):
    __tablename__ = "terminals"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TerminalStatus] = mapped_column(
        enum_type(TerminalStatus), nullable=False, server_default=TerminalStatus.OPERATIONAL.value
    )

    gates: Mapped[list["Gate"]] = relationship(back_populates="terminal")

    __table_args__ = (CheckConstraint("capacity > 0", name="capacity_positive"),)


class Gate(Base, TimestampMixin):
    __tablename__ = "gates"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    terminal_id: Mapped[int] = mapped_column(
        ForeignKey("terminals.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    gate_number: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[GateStatus] = mapped_column(
        enum_type(GateStatus), nullable=False, server_default=GateStatus.AVAILABLE.value
    )

    terminal: Mapped["Terminal"] = relationship(back_populates="gates")
    assignments: Mapped[list["GateAssignment"]] = relationship(back_populates="gate")
    checkpoints: Mapped[list["SecurityCheckpoint"]] = relationship(back_populates="gate")

    __table_args__ = (
        # The original allowed two "Gate 5"s in the same terminal.
        UniqueConstraint("terminal_id", "gate_number", name="uq_gates_terminal_id_gate_number"),
    )


class GateAssignment(Base, TimestampMixin):
    """Booking of a gate by a flight for a time window.

    Not present in the original schema, which tracked only a single `Status`
    column per gate and therefore could not answer "which flight is at gate 5
    at 14:00?" or prevent double-booking.
    """

    __tablename__ = "gate_assignments"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    gate_id: Mapped[int] = mapped_column(
        ForeignKey("gates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    flight_id: Mapped[int] = mapped_column(
        ForeignKey("flights.id", ondelete="CASCADE"), nullable=False, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    gate: Mapped["Gate"] = relationship(back_populates="assignments")
    flight: Mapped["Flight"] = relationship(back_populates="gate_assignments")

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ends_after_starts"),
        # Overlap prevention pushed into PostgreSQL via a GiST exclusion
        # constraint (requires btree_gist). An app-level "is the gate free?"
        # query cannot survive two concurrent assignment requests; this can.
        ExcludeConstraint(
            ("gate_id", "="),
            (literal_column("tstzrange(starts_at, ends_at)"), "&&"),
            name="gate_assignments_no_overlap",
            using="gist",
            where=text("cancelled_at IS NULL"),
        ),
    )


class Runway(Base, TimestampMixin):
    __tablename__ = "runways"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    runway_number: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    status: Mapped[RunwayStatus] = mapped_column(
        enum_type(RunwayStatus), nullable=False, server_default=RunwayStatus.AVAILABLE.value
    )


class MaintenanceSchedule(Base, TimestampMixin):
    __tablename__ = "maintenance_schedule"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    type: Mapped[MaintenanceType] = mapped_column(enum_type(MaintenanceType), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )

    employee: Mapped["Employee | None"] = relationship(back_populates="maintenance_tasks")


class Baggage(Base, TimestampMixin):
    """A checked bag.

    The original schema hung baggage off (PassengerID, FlightID), which permits
    a bag whose passenger never bought a ticket on that flight. Hanging it off
    the ticket makes that state unrepresentable.
    """

    __tablename__ = "baggage"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tag_number: Mapped[str] = mapped_column(String(12), nullable=False, unique=True, index=True)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    status: Mapped[BaggageStatus] = mapped_column(
        enum_type(BaggageStatus),
        nullable=False,
        server_default=BaggageStatus.CHECKED_IN.value,
        index=True,
    )

    ticket: Mapped["Ticket"] = relationship(back_populates="baggage")

    __table_args__ = (
        CheckConstraint("weight_kg > 0 AND weight_kg <= 100", name="weight_kg_within_limits"),
    )


class SecurityCheckpoint(Base, TimestampMixin):
    __tablename__ = "security_checkpoints"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    location: Mapped[str] = mapped_column(String(50), nullable=False)
    gate_id: Mapped[int | None] = mapped_column(
        ForeignKey("gates.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[CheckpointStatus] = mapped_column(
        enum_type(CheckpointStatus), nullable=False, server_default=CheckpointStatus.ACTIVE.value
    )

    gate: Mapped["Gate | None"] = relationship(back_populates="checkpoints")


class Immigration(Base, TimestampMixin):
    __tablename__ = "immigration"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    passenger_id: Mapped[int] = mapped_column(
        ForeignKey("passengers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    flight_id: Mapped[int] = mapped_column(
        ForeignKey("flights.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[ImmigrationStatus] = mapped_column(
        enum_type(ImmigrationStatus),
        nullable=False,
        server_default=ImmigrationStatus.PENDING.value,
        index=True,
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    passenger: Mapped["Passenger"] = relationship(back_populates="immigration_records")
    flight: Mapped["Flight"] = relationship()

    __table_args__ = (
        # One immigration record per passenger per flight.
        UniqueConstraint("passenger_id", "flight_id", name="uq_immigration_passenger_id_flight_id"),
        CheckConstraint(
            "(status = 'pending') = (processed_at IS NULL)",
            name="processed_at_matches_status",
        ),
    )


class AirlineStaff(Base, TimestampMixin):
    __tablename__ = "airline_staff"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    airline_id: Mapped[int] = mapped_column(
        ForeignKey("airlines.id", ondelete="CASCADE"), nullable=False, index=True
    )

    airline: Mapped["Airline"] = relationship(back_populates="staff")


class Cargo(Base, TimestampMixin):
    __tablename__ = "cargo"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    flight_id: Mapped[int] = mapped_column(
        ForeignKey("flights.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[CargoStatus] = mapped_column(
        enum_type(CargoStatus), nullable=False, server_default=CargoStatus.LOADED.value
    )

    flight: Mapped["Flight"] = relationship(back_populates="cargo")

    __table_args__ = (CheckConstraint("weight_kg > 0", name="weight_kg_positive"),)


class FlightCrewSchedule(Base, TimestampMixin):
    __tablename__ = "flight_crew_schedule"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    # The original declared CrewMemberID INT NOT NULL with no foreign key at all,
    # so it happily referenced employees that did not exist.
    crew_member_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    flight_id: Mapped[int] = mapped_column(
        ForeignKey("flights.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[CrewRole] = mapped_column(enum_type(CrewRole), nullable=False)

    crew_member: Mapped["Employee"] = relationship(back_populates="crew_assignments")
    flight: Mapped["Flight"] = relationship(back_populates="crew")

    __table_args__ = (
        UniqueConstraint(
            "flight_id", "crew_member_id", name="uq_flight_crew_schedule_flight_id_crew_member_id"
        ),
    )

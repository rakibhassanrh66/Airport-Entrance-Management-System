"""Domain enumerations.

These are stored as VARCHAR + CHECK constraint rather than native PostgreSQL
enums: adding a value later is a plain constraint swap instead of an
ALTER TYPE that cannot run inside a transaction on older servers.
"""

from enum import StrEnum


class StaffRole(StrEnum):
    ADMIN = "admin"
    OPS = "ops"
    CHECKIN = "checkin"
    SECURITY = "security"


class FlightStatus(StrEnum):
    SCHEDULED = "scheduled"
    DELAYED = "delayed"
    BOARDING = "boarding"
    DEPARTED = "departed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TicketClass(StrEnum):
    ECONOMY = "economy"
    BUSINESS = "business"
    FIRST = "first"


class BookingStatus(StrEnum):
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CANCELLED = "cancelled"


class TerminalStatus(StrEnum):
    OPERATIONAL = "operational"
    UNDER_MAINTENANCE = "under_maintenance"


class GateStatus(StrEnum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    MAINTENANCE = "maintenance"


class RunwayStatus(StrEnum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    MAINTENANCE = "maintenance"


class MaintenanceType(StrEnum):
    RUNWAY = "runway"
    AIRCRAFT = "aircraft"
    GATE = "gate"


class BaggageStatus(StrEnum):
    CHECKED_IN = "checked_in"
    IN_TRANSIT = "in_transit"
    LOADED = "loaded"
    DELIVERED = "delivered"
    LOST = "lost"


class CheckpointStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class WeatherCondition(StrEnum):
    SUNNY = "sunny"
    RAINY = "rainy"
    STORMY = "stormy"
    CLOUDY = "cloudy"


class ImmigrationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CargoStatus(StrEnum):
    LOADED = "loaded"
    IN_TRANSIT = "in_transit"
    UNLOADED = "unloaded"


class CrewRole(StrEnum):
    PILOT = "pilot"
    CO_PILOT = "co_pilot"
    CABIN_CREW = "cabin_crew"


class LoungeStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class ParkingStatus(StrEnum):
    AVAILABLE = "available"
    FULL = "full"


class EmergencyType(StrEnum):
    FIRE = "fire"
    MEDICAL = "medical"
    SECURITY = "security"


#: Legal flight status transitions. Anything absent is rejected by the service layer.
FLIGHT_STATUS_TRANSITIONS: dict[FlightStatus, frozenset[FlightStatus]] = {
    FlightStatus.SCHEDULED: frozenset(
        {FlightStatus.DELAYED, FlightStatus.BOARDING, FlightStatus.CANCELLED}
    ),
    FlightStatus.DELAYED: frozenset(
        {FlightStatus.DELAYED, FlightStatus.BOARDING, FlightStatus.CANCELLED}
    ),
    FlightStatus.BOARDING: frozenset({FlightStatus.DEPARTED, FlightStatus.CANCELLED}),
    FlightStatus.DEPARTED: frozenset({FlightStatus.COMPLETED}),
    FlightStatus.COMPLETED: frozenset(),
    FlightStatus.CANCELLED: frozenset(),
}

#: Legal baggage transitions. Baggage may be declared lost from any live state.
BAGGAGE_STATUS_TRANSITIONS: dict[BaggageStatus, frozenset[BaggageStatus]] = {
    BaggageStatus.CHECKED_IN: frozenset(
        {BaggageStatus.IN_TRANSIT, BaggageStatus.LOADED, BaggageStatus.LOST}
    ),
    BaggageStatus.IN_TRANSIT: frozenset(
        {BaggageStatus.LOADED, BaggageStatus.DELIVERED, BaggageStatus.LOST}
    ),
    BaggageStatus.LOADED: frozenset(
        {BaggageStatus.IN_TRANSIT, BaggageStatus.DELIVERED, BaggageStatus.LOST}
    ),
    BaggageStatus.DELIVERED: frozenset(),
    BaggageStatus.LOST: frozenset({BaggageStatus.DELIVERED}),
}

#: Booking states that still occupy a seat.
ACTIVE_BOOKING_STATUSES: frozenset[BookingStatus] = frozenset(
    {BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN}
)

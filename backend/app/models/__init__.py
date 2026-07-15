"""Model registry.

Every mapped class must be imported here: Alembic's autogenerate and
SQLAlchemy's relationship resolution both work off the populated registry.
"""

from app.db.base import Base
from app.models.ancillary import (
    DutyFreePurchase,
    EmergencyContact,
    EmergencyProtocol,
    FuelStation,
    HotelReservation,
    LostAndFound,
    ParkingLot,
    TaxiService,
    VIPLounge,
    WeatherInfo,
)
from app.models.operations import (
    Airline,
    AirlineStaff,
    Baggage,
    Cargo,
    Employee,
    Flight,
    FlightCrewSchedule,
    Gate,
    GateAssignment,
    Immigration,
    MaintenanceSchedule,
    Passenger,
    Runway,
    SecurityCheckpoint,
    StaffUser,
    Terminal,
    Ticket,
)

__all__ = [
    "Airline",
    "AirlineStaff",
    "Baggage",
    "Base",
    "Cargo",
    "DutyFreePurchase",
    "EmergencyContact",
    "EmergencyProtocol",
    "Employee",
    "Flight",
    "FlightCrewSchedule",
    "FuelStation",
    "Gate",
    "GateAssignment",
    "HotelReservation",
    "Immigration",
    "LostAndFound",
    "MaintenanceSchedule",
    "ParkingLot",
    "Passenger",
    "Runway",
    "SecurityCheckpoint",
    "StaffUser",
    "TaxiService",
    "Terminal",
    "Ticket",
    "VIPLounge",
    "WeatherInfo",
]

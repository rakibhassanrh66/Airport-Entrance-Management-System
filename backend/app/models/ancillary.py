"""Supporting reference tables.

These carry no behaviour beyond storage and referential integrity, so they stay
deliberately thin. They are modelled (rather than dropped) so the schema remains
a faithful superset of the original Main_databse.sql.
"""

from datetime import date, time
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models._types import enum_type
from app.models.enums import (
    EmergencyType,
    LoungeStatus,
    ParkingStatus,
    WeatherCondition,
)

if TYPE_CHECKING:
    from app.models.operations import Passenger


class FuelStation(Base, TimestampMixin):
    __tablename__ = "fuel_stations"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    location: Mapped[str] = mapped_column(String(50), nullable=False)
    capacity_litres: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    __table_args__ = (CheckConstraint("capacity_litres > 0", name="capacity_litres_positive"),)


class WeatherInfo(Base, TimestampMixin):
    __tablename__ = "weather_info"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    observed_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    observed_time: Mapped[time] = mapped_column(Time, nullable=False)
    conditions: Mapped[WeatherCondition] = mapped_column(
        enum_type(WeatherCondition), nullable=False
    )


class VIPLounge(Base, TimestampMixin):
    __tablename__ = "vip_lounges"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[LoungeStatus] = mapped_column(
        enum_type(LoungeStatus), nullable=False, server_default=LoungeStatus.OPEN.value
    )

    __table_args__ = (CheckConstraint("capacity > 0", name="capacity_positive"),)


class TaxiService(Base, TimestampMixin):
    __tablename__ = "taxi_services"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    driver_name: Mapped[str] = mapped_column(String(100), nullable=False)
    license_no: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)


class LostAndFound(Base, TimestampMixin):
    __tablename__ = "lost_and_found"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    found_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    claimed_by_passenger_id: Mapped[int | None] = mapped_column(
        ForeignKey("passengers.id", ondelete="SET NULL"), index=True
    )


class DutyFreePurchase(Base, TimestampMixin):
    __tablename__ = "duty_free_purchases"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    passenger_id: Mapped[int] = mapped_column(
        ForeignKey("passengers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    item_name: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    __table_args__ = (CheckConstraint("price >= 0", name="price_non_negative"),)


class EmergencyContact(Base, TimestampMixin):
    __tablename__ = "emergency_contacts"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    relation: Mapped[str] = mapped_column(String(50), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    passenger_id: Mapped[int] = mapped_column(
        ForeignKey("passengers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    passenger: Mapped["Passenger"] = relationship(back_populates="emergency_contacts")


class ParkingLot(Base, TimestampMixin):
    __tablename__ = "parking_lots"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    location: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ParkingStatus] = mapped_column(
        enum_type(ParkingStatus), nullable=False, server_default=ParkingStatus.AVAILABLE.value
    )

    __table_args__ = (CheckConstraint("capacity > 0", name="capacity_positive"),)


class HotelReservation(Base, TimestampMixin):
    __tablename__ = "hotel_reservations"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    hotel_name: Mapped[str] = mapped_column(String(100), nullable=False)
    check_in_date: Mapped[date] = mapped_column(Date, nullable=False)
    check_out_date: Mapped[date] = mapped_column(Date, nullable=False)
    passenger_id: Mapped[int] = mapped_column(
        ForeignKey("passengers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint("check_out_date > check_in_date", name="check_out_after_check_in"),
    )


class EmergencyProtocol(Base, TimestampMixin):
    __tablename__ = "emergency_protocols"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    type: Mapped[EmergencyType] = mapped_column(enum_type(EmergencyType), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

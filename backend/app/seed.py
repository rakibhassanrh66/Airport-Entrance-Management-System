"""Seed the database with demo data.

Idempotent: safe to run repeatedly. Every insert is keyed on a natural unique
column, so a second run updates nothing and duplicates nothing.

    python -m app.seed

The admin password is taken from AIRPORT_SEED_ADMIN_PASSWORD, or generated and
printed once if that is unset. It is never hardcoded -- the PHP prototype this
replaces shipped with root/no-password baked into the page.
"""

import asyncio
import os
import secrets
import sys
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import dispose_engine, get_sessionmaker
from app.models.enums import CargoStatus, CrewRole, FlightStatus, StaffRole
from app.models.operations import (
    Airline,
    Cargo,
    Employee,
    Flight,
    FlightCrewSchedule,
    Gate,
    Passenger,
    Runway,
    StaffUser,
    Terminal,
)
from app.schemas.auth import StaffUserCreate
from app.services.auth import create_staff_user

AIRLINES = [
    ("Biman Bangladesh Airlines", "BG", "Bangladesh"),
    ("US-Bangla Airlines", "BS", "Bangladesh"),
    ("Emirates", "EK", "United Arab Emirates"),
    ("Qatar Airways", "QR", "Qatar"),
    ("Singapore Airlines", "SQ", "Singapore"),
]

ROUTES = [
    ("BG", "BG147", "DAC", "DXB", 6),
    ("BG", "BG201", "DAC", "LHR", 10),
    ("BS", "BS321", "DAC", "CGP", 1),
    ("EK", "EK585", "DAC", "DXB", 5),
    ("QR", "QR641", "DAC", "DOH", 5),
    ("SQ", "SQ447", "DAC", "SIN", 4),
]

PASSENGERS = [
    ("Rakib", "Hassan", date(1999, 4, 12), "BX1234567", "Bangladesh"),
    ("Ayesha", "Rahman", date(1995, 2, 3), "BX7654321", "Bangladesh"),
    ("Tanvir", "Ahmed", date(1988, 11, 20), "BX1112223", "Bangladesh"),
    ("Fatima", "Khatun", date(2001, 7, 5), "BX9998887", "Bangladesh"),
]


#: Overridable, because a real deployment seeds its own admin address.
#: Note this must be a routable domain: reserved TLDs such as .local and .test
#: are rejected by the same EmailStr validation the login endpoint applies, so
#: seeding one would create an account that could never authenticate.
DEFAULT_ADMIN_EMAIL = "admin@airport.example.com"


async def _seed_staff(session: AsyncSession) -> tuple[str, str | None]:
    email = os.environ.get("AIRPORT_SEED_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).lower()

    existing = await session.scalar(select(StaffUser).where(StaffUser.email == email))
    if existing is not None:
        return email, None

    password = os.environ.get("AIRPORT_SEED_ADMIN_PASSWORD") or secrets.token_urlsafe(16)

    # Go through the same schema the API uses, so a seeded account is always one
    # the login endpoint will actually accept.
    payload = StaffUserCreate(
        email=email,
        full_name="Seed Administrator",
        password=password,
        role=StaffRole.ADMIN,
    )
    await create_staff_user(session, payload)
    return email, password


async def _seed_airlines(session: AsyncSession) -> dict[str, int]:
    codes: dict[str, int] = {}
    for name, iata, country in AIRLINES:
        airline = await session.scalar(select(Airline).where(Airline.iata_code == iata))
        if airline is None:
            airline = Airline(name=name, iata_code=iata, country=country)
            session.add(airline)
            await session.flush()
        codes[iata] = airline.id
    await session.commit()
    return codes


async def _seed_infrastructure(session: AsyncSession) -> None:
    for name, capacity in (("Terminal 1", 4000), ("Terminal 2", 6000), ("Terminal 3", 9000)):
        if await session.scalar(select(Terminal).where(Terminal.name == name)) is None:
            session.add(Terminal(name=name, capacity=capacity))
    await session.commit()

    terminals = list(await session.scalars(select(Terminal).order_by(Terminal.name)))
    for terminal in terminals:
        prefix = terminal.name.split()[-1]
        for i in range(1, 5):
            gate_number = f"{prefix}{i}"
            exists = await session.scalar(
                select(Gate).where(Gate.terminal_id == terminal.id, Gate.gate_number == gate_number)
            )
            if exists is None:
                session.add(Gate(terminal_id=terminal.id, gate_number=gate_number))
    await session.commit()

    for number in ("14L", "14R", "32L"):
        if await session.scalar(select(Runway).where(Runway.runway_number == number)) is None:
            session.add(Runway(runway_number=number))
    await session.commit()


async def _seed_flights(session: AsyncSession, airline_ids: dict[str, int]) -> None:
    base = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(days=1)

    for offset, (iata, number, src, dst, hours) in enumerate(ROUTES):
        if await session.scalar(select(Flight).where(Flight.flight_number == number)):
            continue
        depart = base + timedelta(hours=offset * 3)
        session.add(
            Flight(
                flight_number=number,
                airline_id=airline_ids[iata],
                source=src,
                destination=dst,
                departure_time=depart,
                arrival_time=depart + timedelta(hours=hours),
                status=FlightStatus.SCHEDULED,
                seat_capacity=180,
            )
        )
    await session.commit()


async def _seed_people(session: AsyncSession) -> None:
    for first, last, dob, passport, nationality in PASSENGERS:
        exists = await session.scalar(
            select(Passenger).where(Passenger.passport_number == passport)
        )
        if exists is None:
            session.add(
                Passenger(
                    first_name=first,
                    last_name=last,
                    date_of_birth=dob,
                    passport_number=passport,
                    nationality=nationality,
                )
            )
    await session.commit()

    staff = [
        ("Imran Chowdhury", "Gate Agent", "Ground Operations", 42000),
        ("Nusrat Jahan", "Air Traffic Controller", "ATC", 85000),
        ("Sabbir Alam", "Maintenance Engineer", "Engineering", 61000),
    ]
    for name, role, department, salary in staff:
        exists = await session.scalar(select(Employee).where(Employee.name == name))
        if exists is None:
            session.add(Employee(name=name, role=role, department=department, salary=salary))
    await session.commit()


async def _seed_operations(session: AsyncSession) -> None:
    """Roster crew and load some cargo, so those endpoints show real data.

    Each employee is rostered onto a distinct flight, which sidesteps the
    crew-overlap exclusion by construction: one person never appears twice.
    """
    employees = list(await session.scalars(select(Employee).order_by(Employee.name)))
    flights = list(await session.scalars(select(Flight).order_by(Flight.flight_number)))
    if not employees or not flights:
        return

    roles = [CrewRole.PILOT, CrewRole.CO_PILOT, CrewRole.CABIN_CREW]
    for employee, flight, role in zip(employees, flights, roles, strict=False):
        exists = await session.scalar(
            select(FlightCrewSchedule).where(
                FlightCrewSchedule.crew_member_id == employee.id,
                FlightCrewSchedule.flight_id == flight.id,
            )
        )
        if exists is None:
            session.add(
                FlightCrewSchedule(
                    crew_member_id=employee.id,
                    flight_id=flight.id,
                    role=role,
                    starts_at=flight.departure_time,
                    ends_at=flight.arrival_time,
                )
            )
    await session.commit()

    for flight in flights[:2]:
        if await session.scalar(select(Cargo).where(Cargo.flight_id == flight.id)) is None:
            session.add(Cargo(flight_id=flight.id, weight_kg=1500, status=CargoStatus.LOADED))
    await session.commit()


async def main() -> None:
    async with get_sessionmaker()() as session:
        email, password = await _seed_staff(session)
        airline_ids = await _seed_airlines(session)
        await _seed_infrastructure(session)
        await _seed_flights(session, airline_ids)
        await _seed_people(session)
        await _seed_operations(session)

    await dispose_engine()

    print("Seed complete.")
    if password is not None:
        print(f"  Admin login: {email}")
        print(f"  Password:    {password}")
        print("  (shown once -- store it now)")
    else:
        print(f"  Admin {email} already existed; password unchanged.")


if __name__ == "__main__":
    # psycopg's async driver cannot run on Windows' default ProactorEventLoop.
    # loop_factory is the non-deprecated way to choose one (set_event_loop_policy
    # is slated for removal in Python 3.16).
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(main(), loop_factory=loop_factory)

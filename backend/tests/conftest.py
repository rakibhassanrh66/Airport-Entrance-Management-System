"""Test harness.

Tests run against a real PostgreSQL database, not SQLite. The rules this project
cares about — partial unique indexes, GiST exclusion constraints, FOR UPDATE
locking — do not exist or do not behave the same on SQLite, so testing against
it would prove nothing about production.

The schema is built by running the real Alembic migrations, so every test run
also re-verifies that migrations apply cleanly.
"""

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DB_NAME = "airport_ops_test"


if sys.platform == "win32":

    def pytest_asyncio_loop_factories(config, item):
        """Force a selector-based loop on Windows.

        psycopg's async driver refuses to run on the ProactorEventLoop, which is
        Python's default on Windows. This is the supported replacement for the
        deprecated event_loop_policy fixture.

        Defined under the platform check rather than returning None off Windows:
        pytest-asyncio treats "no hookimpl registered" as no opinion, but an
        implementation that returns None is a UsageError, which aborts
        collection on every non-Windows machine. Leaving the hook undefined lets
        the plugin apply its own default.
        """
        return {"selector": asyncio.SelectorEventLoop}


def _build_test_url() -> str:
    """Point the whole app at a dedicated test database before settings load."""
    from dotenv import dotenv_values  # noqa: PLC0415

    values = dotenv_values(".env")
    base = os.environ.get("AIRPORT_DATABASE_URL") or values.get("AIRPORT_DATABASE_URL")
    if not base:
        raise RuntimeError("AIRPORT_DATABASE_URL is not set; copy .env.example to .env first")

    url, _, _ = base.rpartition("/")
    return f"{url}/{TEST_DB_NAME}"


def _admin_dsn(test_url: str) -> str:
    """A libpq DSN for the maintenance database, used to CREATE/DROP the test DB."""
    dsn = test_url.replace("postgresql+psycopg://", "postgresql://")
    return dsn.rsplit("/", 1)[0] + "/postgres"


TEST_DATABASE_URL = _build_test_url()

# Must happen before app.core.config is imported anywhere.
os.environ["AIRPORT_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["AIRPORT_ENVIRONMENT"] = "test"
os.environ.setdefault("AIRPORT_JWT_SECRET", "test-secret-that-is-definitely-long-enough-32")


@pytest.fixture(scope="session", autouse=True)
def _create_test_database() -> AsyncIterator[None]:
    with psycopg.connect(_admin_dsn(TEST_DATABASE_URL), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')

    from alembic.config import Config  # noqa: PLC0415

    from alembic import command  # noqa: PLC0415

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    yield

    with psycopg.connect(_admin_dsn(TEST_DATABASE_URL), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')


@pytest.fixture
async def engine():
    """Function-scoped on purpose.

    pytest-asyncio gives each test its own event loop, and an asyncpg/psycopg
    connection pool is bound to the loop that created it. A session-scoped
    engine would be pinned to the first test's loop and fail in every later one.
    """
    eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    """One session per test, wrapped in a transaction that is always rolled back.

    join_transaction_mode="create_savepoint" means the service layer's own
    session.commit() calls turn into savepoint releases, so application code runs
    unmodified while the outer transaction still discards everything afterwards.
    """
    conn = await engine.connect()
    trans = await conn.begin()

    maker = async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    async with maker() as s:
        yield s

    await trans.rollback()
    await conn.close()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An HTTP client whose requests reuse the test's rolled-back session."""
    from app.db.session import get_session  # noqa: PLC0415
    from app.main import app  # noqa: PLC0415

    async def _override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- auth fixtures


@pytest.fixture
async def admin_user(session: AsyncSession):
    from app.models.enums import StaffRole  # noqa: PLC0415
    from app.schemas.auth import StaffUserCreate  # noqa: PLC0415
    from app.services.auth import create_staff_user  # noqa: PLC0415

    return await create_staff_user(
        session,
        StaffUserCreate(
            email="admin@airport.example.com",
            full_name="Ops Admin",
            password="correct-horse-battery-staple",
            role=StaffRole.ADMIN,
        ),
    )


@pytest.fixture
async def security_user(session: AsyncSession):
    from app.models.enums import StaffRole  # noqa: PLC0415
    from app.schemas.auth import StaffUserCreate  # noqa: PLC0415
    from app.services.auth import create_staff_user  # noqa: PLC0415

    return await create_staff_user(
        session,
        StaffUserCreate(
            email="security@airport.example.com",
            full_name="Border Officer",
            password="correct-horse-battery-staple",
            role=StaffRole.SECURITY,
        ),
    )


def auth_headers(user) -> dict[str, str]:
    from app.services.auth import issue_tokens  # noqa: PLC0415

    return {"Authorization": f"Bearer {issue_tokens(user).access_token}"}


@pytest.fixture
async def admin_headers(admin_user) -> dict[str, str]:
    return auth_headers(admin_user)


# --------------------------------------------------------------------------- domain fixtures


@pytest.fixture
async def airline(session: AsyncSession):
    from app.models.operations import Airline  # noqa: PLC0415

    a = Airline(name="Biman Bangladesh Airlines", iata_code="BG", country="Bangladesh")
    session.add(a)
    await session.commit()
    await session.refresh(a)
    return a


@pytest.fixture
async def flight(session: AsyncSession, airline):
    from app.models.operations import Flight  # noqa: PLC0415

    depart = datetime.now(UTC) + timedelta(days=7)
    f = Flight(
        flight_number="BG147",
        airline_id=airline.id,
        source="DAC",
        destination="DXB",
        departure_time=depart,
        arrival_time=depart + timedelta(hours=6),
        seat_capacity=3,  # small, so "fully booked" is cheap to reach in tests
    )
    session.add(f)
    await session.commit()
    await session.refresh(f)
    return f


@pytest.fixture
async def passenger(session: AsyncSession):
    from datetime import date  # noqa: PLC0415

    from app.models.operations import Passenger  # noqa: PLC0415

    p = Passenger(
        first_name="Rakib",
        last_name="Hassan",
        date_of_birth=date(1999, 4, 12),
        passport_number="BX1234567",
        nationality="Bangladesh",
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


@pytest.fixture
async def other_passenger(session: AsyncSession):
    from datetime import date  # noqa: PLC0415

    from app.models.operations import Passenger  # noqa: PLC0415

    p = Passenger(
        first_name="Ayesha",
        last_name="Rahman",
        date_of_birth=date(1995, 2, 3),
        passport_number="BX7654321",
        nationality="Bangladesh",
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


@pytest.fixture
async def terminal(session: AsyncSession):
    from app.models.operations import Terminal  # noqa: PLC0415

    t = Terminal(name="Terminal 1", capacity=5000)
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


@pytest.fixture
async def gate(session: AsyncSession, terminal):
    from app.models.operations import Gate  # noqa: PLC0415

    g = Gate(terminal_id=terminal.id, gate_number="A1")
    session.add(g)
    await session.commit()
    await session.refresh(g)
    return g

# Airport Operations API

A production-shaped backend for international airport operations: airlines, flight
scheduling, ticketing, gate assignment, baggage tracking and immigration.

FastAPI · PostgreSQL 16 · SQLAlchemy 2 (async) · Alembic · Docker

---

## Quick start

```bash
cd backend
cp .env.example .env          # then fill in the two required secrets, see below
docker compose up -d
```

That starts PostgreSQL, applies migrations, and serves the API on
<http://localhost:8000>. Interactive docs: <http://localhost:8000/docs>.

Load demo data:

```bash
docker compose exec api python -m app.seed
```

The seed prints a generated admin password **once**. Set
`AIRPORT_SEED_ADMIN_PASSWORD` beforehand to choose your own.

### Required configuration

Two variables have no default and the app refuses to boot without them:

| Variable | Notes |
|---|---|
| `POSTGRES_PASSWORD` | Database password. |
| `AIRPORT_JWT_SECRET` | ≥32 chars. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |

This is deliberate. There is no fallback secret to forget about in production.

---

## Local development (without Docker for the app)

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Linux/macOS: .venv/bin/pip
docker compose up -d db                   # database only
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python run_local.py
```

Use `run_local.py` rather than calling `uvicorn` directly on **Windows**:
psycopg's async driver cannot run on Windows' default `ProactorEventLoop`, and
the loop policy must be set before uvicorn builds its loop. On Linux and macOS
either works.

### Tests

```bash
.venv/Scripts/python -m pytest
```

105 tests. They run against a real PostgreSQL database — created, migrated and
dropped automatically — because the guarantees this project relies on (partial
unique indexes, GiST exclusion constraints, `SELECT … FOR UPDATE`) do not exist
on SQLite. Testing against SQLite would prove nothing about production.

Each test runs inside a transaction that is rolled back afterwards, so tests do
not interfere with one another.

---

## Layout

```
app/
├── main.py            app factory, error handling, health/readiness probes
├── core/              config, logging, security primitives, domain errors
├── db/                engine, session lifecycle, declarative base
├── models/            SQLAlchemy models + enums and their legal transitions
├── schemas/           Pydantic request/response contracts
├── services/          business rules — no HTTP imports, independently testable
├── api/v1/            thin routers; they delegate to services
└── seed.py            idempotent demo data
alembic/               migrations
tests/                 pytest suite
```

The service layer raises domain exceptions (`ConflictError`,
`IllegalStateTransitionError`, …) which `main.py` translates into HTTP
responses. Business logic therefore never imports FastAPI and can be tested
without a request cycle.

---

## The rules this API actually enforces

This is the part worth reading. Each rule below is enforced in the **database**,
not merely checked in Python — an application-level check loses to two
concurrent requests, and this is a domain where "two passengers, one seat" is a
real failure.

### One seat, one passenger

A partial unique index on `(flight_id, seat_number)` covering only live bookings:

```sql
CREATE UNIQUE INDEX uq_tickets_flight_seat_active ON tickets (flight_id, seat_number)
  WHERE booking_status IN ('confirmed', 'checked_in');
```

Cancelled tickets fall outside the index, so a released seat can be resold. Two
simultaneous bookings for 12A cannot both succeed; one gets `409`. Capacity is
additionally guarded by locking the flight row `FOR UPDATE`, so two callers
cannot both read "179 of 180 sold" and both proceed.

### One gate, one flight at a time

A GiST exclusion constraint (requires `btree_gist`, created by the migration):

```sql
EXCLUDE USING gist (gate_id WITH =, tstzrange(starts_at, ends_at) WITH &&)
  WHERE (cancelled_at IS NULL)
```

Overlapping windows on the same gate are impossible. Adjacent windows
(10:00–11:00 then 11:00–12:00) are fine, because `tstzrange` is half-open.

### Flights follow a lifecycle

```
scheduled ──> delayed ──> boarding ──> departed ──> completed
     │           │            │
     └───────────┴────────────┴──> cancelled
```

Anything else is rejected with `409 illegal_state_transition`, and the response
lists which transitions *are* legal. Cancelling a flight cascades: live tickets
are cancelled and gate assignments released, so a cancelled flight never keeps a
gate blocked.

### Baggage belongs to a ticket

Baggage hangs off `ticket_id`, not off `(passenger_id, flight_id)`. A bag for a
passenger who was never booked on the flight is therefore unrepresentable rather
than merely discouraged.

### Immigration requires a real booking

A case can only be opened for a passenger holding a live ticket on that flight,
and can only be decided once.

---

## Roles

| Role | May do |
|---|---|
| `admin` | everything (superset of all roles) |
| `ops` | airlines, flights, terminals, gates, gate assignments |
| `checkin` | passengers, tickets, check-in, baggage |
| `security` | immigration cases and decisions |

Authentication is a bearer JWT from `POST /api/v1/auth/login`. Access tokens are
short-lived; refresh tokens are accepted **only** by `/auth/refresh` and are
rejected anywhere else. Passwords are hashed with argon2 and transparently
rehashed when parameters change.

---

## How this schema differs from `Devfiles/WEB and SQL/Main_databse.sql`

All 25 original tables are present. The following were defects, and are fixed:

| Original | Problem | Now |
|---|---|---|
| `INT PRIMARY KEY` supplied by the client | two clients pick the same id | `GENERATED BY DEFAULT AS IDENTITY` |
| `FlightCrewSchedule.CrewMemberID INT NOT NULL` | no foreign key at all — referenced employees that never existed | FK to `employees` |
| `Baggage(PassengerID, FlightID)` | bags for passengers with no ticket | FK to `tickets` |
| No seat constraint | the same seat sellable twice | partial unique index |
| `Gates.Status` only | could not say *which* flight held a gate, or prevent double-booking | `gate_assignments` + exclusion constraint |
| No `CHECK` constraints | flights arriving before departure; negative salaries | checks throughout |
| No indexes | every foreign-key lookup a sequential scan | indexed FKs and filter columns |
| No timestamps | no audit trail | `created_at` / `updated_at` on every table |
| Two `Gate 5`s per terminal | ambiguous | unique `(terminal_id, gate_number)` |

Two tables are additions: `gate_assignments` (above) and `staff_users` (API
logins, kept separate from the `employees` HR record — a person can be an
employee without holding a login).

Enums are stored as `VARCHAR` + `CHECK` rather than native PostgreSQL enums, so
adding a value later is a constraint swap instead of an `ALTER TYPE`.

---

## Security notes

The PHP prototype this replaces (`Devfiles/WEB and SQL/webfile.html`) connected
as `root` with an empty password, built SQL by string concatenation, and echoed
database values into HTML unescaped. For the record, here:

- Credentials come from the environment; none are committed. `.env` is gitignored.
- Every query is parameterised through SQLAlchemy. There is no string-built SQL.
- Login failures are indistinguishable whether or not the email exists, and
  cost the same time, so the endpoint cannot be used to enumerate accounts.
- Interactive docs and the OpenAPI schema are disabled when
  `AIRPORT_ENVIRONMENT=production`.
- The container runs as an unprivileged user.

---

## Endpoints

29 routes under `/api/v1`. Full interactive reference at `/docs`.

| Area | Highlights |
|---|---|
| auth | `login`, `refresh`, `me`, `staff` (admin only) |
| flights | list/filter, create, `PATCH /{id}/status`, `GET /{id}/seats` |
| tickets | book, `check-in`, `cancel` |
| passengers | register, search by name/nationality |
| gates | terminals, gates, `gate-assignments`, `GET /gates/{id}/schedule` |
| baggage | check in, `by-tag/{tag}`, `PATCH /{id}/status` |
| immigration | open case, `POST /{id}/decision` |

Liveness at `/health` (no database), readiness at `/ready` (checks the database).

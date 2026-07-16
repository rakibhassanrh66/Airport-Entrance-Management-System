# Demoing this project

**Demo:** <https://airport-entrance-management.vercel.app> (the page to show)
**Swagger:** <https://airport-entrance-management.vercel.app/docs>
**Login:** `admin@airport.example.com` / `AirportDemo2026!`

> The domain is `airport-entrance-management`, **not** `…-management-system`.
> Vercel truncated the project name when it built the alias, and the longer
> name resolves to `DEPLOYMENT_NOT_FOUND`.

There is a second, independent stack on Render — same code, its own database:
<https://airport-entrance-management-system.onrender.com/docs>

> Render's free instance sleeps after ~15 minutes idle and the first request
> takes **~50 seconds** to wake. Vercel does not sleep, which is why it is the
> one to demo. If you are showing Render, warm it up first.

---

## The 60-second version

> "It's an airport operations backend — flights, ticketing, gates, baggage,
> immigration. 58 endpoints, 152 tests, running on Vercel and on Render.
>
> The part I'd point at is that the business rules are enforced in PostgreSQL,
> not in Python. Two people can't book the same seat — and not because I check
> first, because a partial unique index makes it impossible. An `if seat_is_free`
> check loses to two simultaneous requests; a database constraint doesn't."

That answers "what did you build" and "what was hard" in one breath.

---

## The demo that lands: two people, one seat

This is the whole project in fifteen seconds. Don't lead with the schema.

**Set-up line:** *"Almost every CRUD app has a race condition in it. Here's mine
not having one."*

Save this as `race.py` and run it:

```python
import json, threading, urllib.request, urllib.error

BASE = "https://airport-entrance-management-system.onrender.com"
SEAT = "15B"          # pick an unused seat each time you demo

def call(method, path, token=None, body=None):
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body else None
    try:
        with urllib.request.urlopen(req, data, timeout=90) as r:
            return r.status, json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "{}")

_, tok = call("POST", "/api/v1/auth/login",
              body={"email": "admin@airport.example.com",
                    "password": "AirportDemo2026!"})
token = tok["access_token"]

results, barrier = {}, threading.Barrier(2)

def book(tag, passenger_id):
    barrier.wait()                     # both released at the same instant
    results[tag] = call("POST", "/api/v1/tickets", token, {
        "flight_id": 1, "passenger_id": passenger_id, "seat_number": SEAT,
        "ticket_class": "economy", "price": "450.00"})

a = threading.Thread(target=book, args=("A", 1))
b = threading.Thread(target=book, args=("B", 3))
a.start(); b.start(); a.join(); b.join()
for tag, (status, body) in results.items():
    print(f"Request {tag}: {status} {body.get('code') or 'CREATED'} "
          f"{body.get('message') or 'seat ' + str(body.get('seat_number'))}")
```

Real output:

```
Request A: 409 conflict  Seat 14C is already taken on this flight.
Request B: 201 CREATED   seat 14C
```

**The line to say:** *"Both requests were released by a barrier, so they hit the
server at the same moment. One got a 409. That's not my code choosing — it's
this:"*

```sql
CREATE UNIQUE INDEX uq_tickets_flight_seat_active ON tickets (flight_id, seat_number)
  WHERE booking_status IN ('confirmed', 'checked_in');
```

*"It's partial — cancelled tickets fall outside it, so a released seat resells.
And capacity is guarded separately by locking the flight row `FOR UPDATE`, so
two callers can't both read '179 of 180 sold' and both proceed."*

**Change the seat number between runs**, or you'll demo a 409 against your own
earlier booking rather than a live race.

---

## Browser demo (no terminal)

1. Open **`/docs`** — Swagger UI.
2. `POST /api/v1/auth/login` → **Try it out** → the credentials above → **Execute**.
3. Copy `access_token` from the response.
4. Click **Authorize** (top right), paste it, **Authorize**.
5. Now anything works. Good ones to click, in order:

| Endpoint | What it shows |
|---|---|
| `GET /api/v1/flights` | 6 seeded flights out of Dhaka |
| `GET /api/v1/flights/1/seats` | live seat map |
| `POST /api/v1/tickets` | book a seat |
| `POST /api/v1/tickets` *(same seat again)* | **409** — the constraint, visibly |
| `PATCH /api/v1/flights/1/status` → `departed` | **409 illegal_state_transition**, and the response *lists the legal ones* |
| `POST /api/v1/crew-assignments` *(same crew member, two overlapping flights)* | **409** — the same seat rule, one axis over: a person can't crew two aircraft at once |

That status one is a great second demo. `scheduled` cannot jump to `departed`.
The error tells you what it *could* have been — an error message that helps
rather than scolds. And crew scheduling is the third instance of the same
idea: a GiST exclusion constraint, this time on `crew_member_id`, so one person
cannot be rostered onto two flights whose times overlap.

---

## If they ask "what would you do next?"

Answer honestly; it lands better than pretending it's finished.

- **10 reference/ancillary tables are modelled and migrated but have no HTTP
  routes** — a deliberate quality-over-surface-area call. The operational tables
  (employees, cargo, crew, runways, maintenance, checkpoints, airline staff) are
  routed; the pure lookups and passenger-attached tables are not.
- **Migrations run at container start.** Fine at one instance; with several it
  wants a proper release phase.
- **Refresh tokens are revoked but not rotated.** A refresh token is reusable
  until it is revoked or expires; rotating it on every use would shrink the
  window further.
- **Revocation costs a lookup per request.** That is the price of logout meaning
  something with self-contained tokens. Short-lived tokens would trade it back.

If they ask what you *fixed*, these three are worth naming, because each has a
story:

- **Logout now revokes.** A signed JWT cannot be un-issued, so client-side
  "logout" left a working credential in anyone's hands who copied it. Every
  token already carried a `jti`; `revoked_tokens` records it and the request
  path refuses it.
- **Login is rate limited in the database, not in memory.** This runs as
  multiple instances on Render and as serverless functions on Vercel, where an
  in-process counter is per-process — so it either resets constantly or guards
  only the one instance that saw the attempts. A shared table is the only place
  the count is true for everyone. The limit deliberately applies to unknown
  emails too, or 429-vs-401 becomes an account-enumeration oracle.
- **CI runs the suite on every push**, against a real `postgres:16`. Its very
  first run caught a bug worth telling: `pytest_asyncio_loop_factories` returned
  `None` off Windows, which pytest-asyncio treats as a fatal `UsageError` — so
  the suite had never once been able to collect on Linux. Every previous "the
  tests pass" was a Windows-only claim.

Naming your own gaps unprompted reads as judgement, not weakness. An interviewer
who finds them for you is a worse outcome than you listing them first.

---

## Questions you'll probably get

**"Why not just check before inserting?"**
Because two requests both pass the check before either inserts. That's not
theoretical — it's the default outcome under any real concurrency. The test
suite has a case that fires two simultaneous bookings and asserts exactly one
wins; it fails if you remove the index.

**"Why is Postgres required for the tests?"**
Partial unique indexes, GiST exclusion constraints and `SELECT … FOR UPDATE`
don't exist on SQLite. A green SQLite suite would prove nothing about
production, so the tests create, migrate and drop a real database.

**"What's the gate thing?"**
A GiST exclusion constraint — `EXCLUDE USING gist (gate_id WITH =,
tstzrange(starts_at, ends_at) WITH &&)`. Overlapping windows on one gate are
unrepresentable. Adjacent ones (10:00–11:00, then 11:00–12:00) are fine because
`tstzrange` is half-open. Worth knowing that detail if you claim the constraint.

**"Why is `Devfiles/` in here?"**
It's the original coursework prototype — a NetBeans console app and a PHP page
that connected as `root` with an empty password. It's kept to show the distance
travelled. Don't gloss over it; the contrast *is* the story.

---

## Before you show anyone

- [ ] Open `/docs` a minute early so the instance is awake.
- [ ] Pick a fresh seat number for the race demo.
- [ ] Have `README.md` open in a second tab — the mermaid diagrams are the
      architecture explanation, so you don't have to draw one.
- [ ] Know the three answers above cold. They are the follow-ups.

---

## Operating it

Deploy config, environment variables and the free-tier traps are in
[DEPLOY.md](DEPLOY.md).

**This is a demo deployment, not production.** `AIRPORT_ENVIRONMENT=staging`
keeps `/docs` public on purpose. Everything else — argon2, JWT, role checks,
every database constraint — is identical to production. If this ever held real
passenger data: set `production`, remove `AIRPORT_SEED_ON_START` and
`AIRPORT_SEED_ADMIN_PASSWORD`, rotate `AIRPORT_JWT_SECRET`, change that admin
password, and close the two auth gaps listed above first.

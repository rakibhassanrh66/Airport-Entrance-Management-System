# Deploying

Two supported targets. **Render is the recommended one** and the one the
repository is shaped for; Vercel works but costs you things, listed below.

---

## What the database must support

Not every managed Postgres will do. This schema depends on:

| Requirement | Why |
|---|---|
| `btree_gist` extension | The exclusion constraint that stops one gate hosting two flights at overlapping times. The migration runs `CREATE EXTENSION IF NOT EXISTS btree_gist`, so the database user needs permission to create it. |
| PostgreSQL 13+ | `tstzrange`, partial unique indexes, `GENERATED … AS IDENTITY`. |

Render Postgres, Neon and Supabase all satisfy both. A provider that blocks
`CREATE EXTENSION` will fail on the first migration — not silently, and not
later.

---

## Render (recommended)

Container-native: it builds `backend/Dockerfile` as-is, so what runs in
production is what runs locally under `docker compose`.

### If your service already exists and the build failed

The characteristic failure is:

```
#1 transferring dockerfile: 2B done
error: failed to solve: failed to read dockerfile: open Dockerfile: no such file or directory
```

Render looked for `Dockerfile` at the repository root. It is at
`backend/Dockerfile`. A service created through the dashboard does **not** read
`render.yaml`, so fix it in the dashboard — **Settings → Build & Deploy**:

| Field | Value |
|---|---|
| Dockerfile Path | `./backend/Dockerfile` |
| Docker Build Context Directory | `./backend` |
| Docker Command | `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"` |
| Health Check Path | `/health` |

Fixing the path alone is not enough. The app has **no fallback secrets by
design** and will exit on boot without these — under **Environment**:

| Variable | Value |
|---|---|
| `AIRPORT_DATABASE_URL` | Internal Connection String of a Render Postgres instance |
| `AIRPORT_JWT_SECRET` | ≥32 chars — `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `AIRPORT_ENVIRONMENT` | `production` |

If you have no database yet, create one first (**New → Postgres**); the web
service alone is not enough.

Render's connection string begins `postgres://`. That is handled — see
[The URL rewrite](#the-url-rewrite) — so paste it unmodified.

### From scratch, via Blueprint

`render.yaml` at the root provisions the database and the web service together,
wires the connection string, and generates the JWT secret:

**New → Blueprint** → pick this repository → Apply.

This creates a *new* service. If you already have one, it keeps its URL only if
you take the dashboard route above.

### Free plan caveats

- The service **spins down after inactivity**; the next request pays ~50s of
  cold start. A first request that appears to hang is usually this.
- Free Postgres instances **expire** after their trial window. Back up anything
  you care about.
- `preDeployCommand` is paid-only, so migrations run at container start instead.
  Alembic takes a lock, so concurrent instances queue rather than collide.

### Verify

```bash
curl https://<your-service>.onrender.com/health   # {"status":"ok"} — no DB touched
curl https://<your-service>.onrender.com/ready    # {"status":"ready","database":"ok"}
```

`/ready` is the honest one: it returns 503 if Postgres is unreachable. If
`/health` passes and `/ready` fails, the container is up and the database wiring
is wrong.

Then seed an admin (**Shell** tab, or a One-Off Job):

```bash
AIRPORT_SEED_ADMIN_PASSWORD='<a real password>' python -m app.seed
```

`/docs` is **disabled** when `AIRPORT_ENVIRONMENT=production`. That is
deliberate, not a broken deploy.

---

## Vercel

Works, but understand the trade before choosing it.

| | Consequence |
|---|---|
| `backend/Dockerfile` is **unused** | Vercel does not build containers. Production and local are no longer the same artifact. |
| Migrations **cannot run** in a function | You run `alembic upgrade head` from your machine against the production database, by hand, at the right moment. |
| Every invocation is a **cold connection** | Requires `AIRPORT_DB_SERVERLESS=true` (NullPool) plus a provider-side pooler. Without both, you exhaust connections under trivial load. |
| Cold starts | argon2 + SQLAlchemy import on a cold function is slow. |

### Setup

1. Database: **Neon** (has `btree_gist`, and a pooler). Take the **pooled**
   connection string, not the direct one.
2. Environment variables:

   | Variable | Value |
   |---|---|
   | `AIRPORT_DATABASE_URL` | Neon **pooled** connection string |
   | `AIRPORT_DB_SERVERLESS` | `true` — **not optional here** |
   | `AIRPORT_JWT_SECRET` | ≥32 chars |
   | `AIRPORT_ENVIRONMENT` | `production` |

3. Migrate from your machine, before the first request:

   ```bash
   cd backend
   AIRPORT_DATABASE_URL='<neon DIRECT url, not pooled>' \
   AIRPORT_JWT_SECRET='<anything ≥32 chars, unused by alembic>' \
     .venv/Scripts/python -m alembic upgrade head
   ```

   Use the **direct** URL for migrations. DDL through a transaction pooler is a
   reliable way to have a bad afternoon.

4. Deploy. `vercel.json` routes every path to `api/index.py`.

Dependencies for this target live in the root `requirements.txt`, duplicated
from `backend/pyproject.toml` because Vercel reads nothing else. Changing one
does not change the other.

---

## The URL rewrite

Render, Neon, Supabase, Railway and Heroku all hand out `postgres://…` or
`postgresql://…`. SQLAlchemy's async engine needs an explicit async driver and
rejects both at connect time.

`Settings._require_async_driver` (`backend/app/core/config.py`) rewrites either
prefix to `postgresql+psycopg://`. Paste the provider's string as-is; an
already-correct `postgresql+psycopg://` URL passes through untouched.

---

## Both targets

- Secrets come from the platform's environment store. Nothing is committed.
- `AIRPORT_ENVIRONMENT=production` disables `/docs`, `/redoc` and
  `/openapi.json`.
- There is **no logout or refresh-token revocation** yet: a stolen token is
  valid until it expires. There is **no login rate limiting**. Both are known
  gaps — weigh them before exposing this to real traffic.

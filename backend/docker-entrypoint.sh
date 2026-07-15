#!/bin/sh
# Migrate, then serve. One command, so no host needs to chain two with "&&".
#
# This exists because Render's dockerCommand is not a shell: it expands $PORT and
# then execs the tokens directly, so "alembic upgrade head && uvicorn ..." passes
# "&&" to alembic as a literal argument and dies with
#   alembic: error: unrecognized arguments: && uvicorn ...
# Wrapping it in sh -c "..." fails differently. Putting the chain in the image
# sidesteps the whole question and keeps local, compose and Render identical.
set -e

alembic upgrade head

# Opt-in demo seeding. Off unless explicitly enabled.
#
# This exists because Render's free Postgres accepts no external connections —
# not even from an allow-listed IP — and one-off jobs and SSH are paid features.
# On that plan there is genuinely no other way in: the only process that can
# reach the database is this container.
#
# app.seed is idempotent; a second run leaves an existing admin's password
# alone. Leave this unset anywhere real data lives.
if [ "${AIRPORT_SEED_ON_START}" = "true" ]; then
    echo "AIRPORT_SEED_ON_START=true - seeding demo data"
    python -m app.seed
fi

# exec so uvicorn becomes PID 1 and receives SIGTERM directly. Without it, the
# shell holds PID 1, swallows the signal, and the platform kills the container
# after its grace period instead of letting connections drain.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

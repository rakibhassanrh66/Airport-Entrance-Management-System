"""Route operational tables; crew no-overlap rule

The operational tables (employees, cargo, runways, maintenance, checkpoints,
airline_staff) already existed from the initial schema — they were modelled and
migrated but never routed, so exposing them needs no DDL.

The one schema change is on flight_crew_schedule, which becomes more than a join
table. It gains the flight's time window (copied on assignment) and, over that
window, a GiST exclusion constraint that forbids one crew member from holding
two live assignments whose flights overlap — the same mechanism as gate overlap,
keyed on crew_member_id instead of gate_id. The old plain unique constraint on
(flight_id, crew_member_id) is replaced by a partial unique index so a released
assignment frees the pair to be rostered again.

Revision ID: 639b811da217
Revises: 3338536fc48e
Create Date: 2026-07-16 14:23:42.020900

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "639b811da217"
down_revision: str | None = "3338536fc48e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "flight_crew_schedule",
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "flight_crew_schedule",
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "flight_crew_schedule",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Replace the whole-table unique constraint with a partial one, so releasing
    # an assignment (cancelled_at set) frees the pair to be rostered again.
    op.drop_constraint(
        op.f("uq_flight_crew_schedule_flight_id_crew_member_id"),
        "flight_crew_schedule",
        type_="unique",
    )
    op.create_index(
        "uq_flight_crew_active",
        "flight_crew_schedule",
        ["flight_id", "crew_member_id"],
        unique=True,
        postgresql_where=sa.text("cancelled_at IS NULL"),
    )

    op.create_check_constraint("ends_after_starts", "flight_crew_schedule", "ends_at > starts_at")
    # btree_gist is already installed by the initial migration (the gate
    # exclusion needs it); CREATE EXTENSION IF NOT EXISTS is a no-op here.
    op.create_exclude_constraint(
        "flight_crew_no_overlap",
        "flight_crew_schedule",
        ("crew_member_id", "="),
        (sa.literal_column("tstzrange(starts_at, ends_at)"), "&&"),
        where=sa.text("cancelled_at IS NULL"),
        using="gist",
    )


def downgrade() -> None:
    # No type_: an exclusion constraint is not one of check/fk/pk/unique, and
    # passing a type_ it does not recognise raises rather than dropping it.
    op.drop_constraint("flight_crew_no_overlap", "flight_crew_schedule")
    op.drop_constraint(
        op.f("ck_flight_crew_schedule_ends_after_starts"),
        "flight_crew_schedule",
        type_="check",
    )
    op.drop_index(
        "uq_flight_crew_active",
        table_name="flight_crew_schedule",
        postgresql_where=sa.text("cancelled_at IS NULL"),
    )
    op.create_unique_constraint(
        op.f("uq_flight_crew_schedule_flight_id_crew_member_id"),
        "flight_crew_schedule",
        ["flight_id", "crew_member_id"],
    )
    op.drop_column("flight_crew_schedule", "cancelled_at")
    op.drop_column("flight_crew_schedule", "ends_at")
    op.drop_column("flight_crew_schedule", "starts_at")

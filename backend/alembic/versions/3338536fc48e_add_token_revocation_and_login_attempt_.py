"""Add token revocation and login attempt tracking

Two gaps this closes:

* A signed JWT cannot be un-issued, so "logout" was previously a client-side
  gesture: the token kept working until it expired. `revoked_tokens` records the
  jti every token already carries, and the request path refuses any jti it finds
  there.
* Nothing limited password guessing. `login_attempts` is the shared counter that
  makes a lockout true across every instance and every serverless invocation,
  which an in-process counter cannot be.

Revision ID: 3338536fc48e
Revises: d7989b52d0ce
Create Date: 2026-07-16 13:28:13.324203

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3338536fc48e"
down_revision: str | None = "d7989b52d0ce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("client_ip", sa.String(length=45), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_attempts")),
    )
    # The lockout question is always "failures for this email since T".
    op.create_index(
        "ix_login_attempts_email_attempted_at",
        "login_attempts",
        ["email", "attempted_at"],
        unique=False,
    )
    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(length=36), nullable=False),
        sa.Column("staff_user_id", sa.Integer(), nullable=False),
        sa.Column("token_type", sa.String(length=10), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
            name=op.f("fk_revoked_tokens_staff_user_id_staff_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("jti", name=op.f("pk_revoked_tokens")),
    )
    # Purging by expiry is the only bulk read this table gets.
    op.create_index(
        op.f("ix_revoked_tokens_expires_at"), "revoked_tokens", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_revoked_tokens_staff_user_id"), "revoked_tokens", ["staff_user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_revoked_tokens_staff_user_id"), table_name="revoked_tokens")
    op.drop_index(op.f("ix_revoked_tokens_expires_at"), table_name="revoked_tokens")
    op.drop_table("revoked_tokens")
    op.drop_index("ix_login_attempts_email_attempted_at", table_name="login_attempts")
    op.drop_table("login_attempts")

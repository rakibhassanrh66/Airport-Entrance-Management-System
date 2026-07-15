import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError, NotFoundError
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.models.enums import StaffRole
from app.models.operations import StaffUser
from app.schemas.auth import StaffUserCreate, TokenPair

logger = logging.getLogger(__name__)


async def create_staff_user(session: AsyncSession, payload: StaffUserCreate) -> StaffUser:
    existing = await session.scalar(
        select(StaffUser).where(StaffUser.email == payload.email.lower())
    )
    if existing is not None:
        raise ConflictError("A staff user with that email already exists.")

    user = StaffUser(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info("staff user created", extra={"staff_user_id": user.id, "role": user.role.value})
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> StaffUser:
    user = await session.scalar(select(StaffUser).where(StaffUser.email == email.lower()))

    if user is None:
        # Hash anyway so a missing account and a wrong password take the same
        # time; otherwise response latency reveals which emails are registered.
        hash_password(password)
        raise AuthenticationError("Incorrect email or password.")

    if not verify_password(password, user.password_hash):
        raise AuthenticationError("Incorrect email or password.")

    if not user.is_active:
        raise AuthenticationError("This account is disabled.")

    # Transparently upgrade the stored hash if argon2's parameters have changed.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(user)

    return user


def issue_tokens(user: StaffUser) -> TokenPair:
    settings = get_settings()
    return TokenPair(
        access_token=create_token(subject=str(user.id), token_type="access", role=user.role.value),
        refresh_token=create_token(subject=str(user.id), token_type="refresh"),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


async def refresh_tokens(session: AsyncSession, refresh_token: str) -> TokenPair:
    payload = decode_token(refresh_token, expected_type="refresh")

    user = await session.get(StaffUser, int(payload["sub"]))
    if user is None:
        raise AuthenticationError("Token refers to an unknown user.")
    if not user.is_active:
        raise AuthenticationError("This account is disabled.")

    return issue_tokens(user)


async def get_active_user(session: AsyncSession, user_id: int) -> StaffUser:
    user = await session.get(StaffUser, user_id)
    if user is None:
        raise NotFoundError("Staff user not found.")
    if not user.is_active:
        raise AuthenticationError("This account is disabled.")
    return user


def ensure_role(user: StaffUser, allowed: set[StaffRole]) -> None:
    from app.core.errors import PermissionDeniedError

    if user.role is StaffRole.ADMIN:
        return  # admin is a superset of every other role
    if user.role not in allowed:
        raise PermissionDeniedError(
            "Your role does not permit this operation.",
            details={"role": user.role.value, "required": sorted(r.value for r in allowed)},
        )

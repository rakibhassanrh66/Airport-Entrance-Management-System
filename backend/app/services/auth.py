import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    RateLimitedError,
)
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.models.enums import StaffRole
from app.models.operations import LoginAttempt, RevokedToken, StaffUser
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


async def _recent_failures(session: AsyncSession, email: str) -> int:
    """Failed attempts for this email that still count against it."""
    settings = get_settings()
    since = datetime.now(UTC) - timedelta(minutes=settings.login_failure_window_minutes)

    # A success clears the slate. Counting every failure in the window
    # regardless would keep an account locked after its owner has already proved
    # who they are — punishing the victim of a guessing attempt, not the guesser.
    last_success_id = await session.scalar(
        select(func.max(LoginAttempt.id)).where(
            LoginAttempt.email == email.lower(),
            LoginAttempt.succeeded.is_(True),
            LoginAttempt.attempted_at >= since,
        )
    )

    query = (
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.email == email.lower(),
            LoginAttempt.succeeded.is_(False),
            LoginAttempt.attempted_at >= since,
        )
    )
    if last_success_id is not None:
        # Order by identity, not by attempted_at. Postgres' now() is the
        # *transaction* start time, so every attempt written inside one
        # transaction carries an identical timestamp and "newer than the last
        # success" silently includes the failures that preceded it. The
        # sequence cannot tie.
        query = query.where(LoginAttempt.id > last_success_id)

    return await session.scalar(query) or 0


async def _record_attempt(
    session: AsyncSession, email: str, client_ip: str | None, *, succeeded: bool
) -> None:
    session.add(LoginAttempt(email=email.lower(), client_ip=client_ip, succeeded=succeeded))
    await session.commit()


async def authenticate(
    session: AsyncSession, email: str, password: str, *, client_ip: str | None = None
) -> StaffUser:
    settings = get_settings()

    if await _recent_failures(session, email) >= settings.login_max_failures:
        # Deliberately the same answer whether or not the account exists: a
        # distinct "locked" response for real accounts only would turn this
        # into an account-enumeration oracle, which is the opposite of the point.
        logger.warning("login rate limited", extra={"email": email.lower()})
        raise RateLimitedError(
            "Too many failed login attempts. Try again later.",
            retry_after_seconds=settings.login_failure_window_minutes * 60,
        )

    user = await session.scalar(select(StaffUser).where(StaffUser.email == email.lower()))

    if user is None:
        # Hash anyway so a missing account and a wrong password take the same
        # time; otherwise response latency reveals which emails are registered.
        hash_password(password)
        await _record_attempt(session, email, client_ip, succeeded=False)
        raise AuthenticationError("Incorrect email or password.")

    if not verify_password(password, user.password_hash):
        await _record_attempt(session, email, client_ip, succeeded=False)
        raise AuthenticationError("Incorrect email or password.")

    if not user.is_active:
        await _record_attempt(session, email, client_ip, succeeded=False)
        raise AuthenticationError("This account is disabled.")

    # Transparently upgrade the stored hash if argon2's parameters have changed.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_login_at = datetime.now(UTC)
    await _record_attempt(session, email, client_ip, succeeded=True)
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


async def is_revoked(session: AsyncSession, jti: str | None) -> bool:
    if jti is None:
        return False
    return await session.get(RevokedToken, jti) is not None


async def _revoke(session: AsyncSession, payload: dict, token_type: str) -> None:
    jti = payload.get("jti")
    if jti is None:
        return  # Nothing to key a revocation on.
    if await session.get(RevokedToken, jti) is not None:
        return  # Already revoked; logging out twice is not an error.

    session.add(
        RevokedToken(
            jti=jti,
            staff_user_id=int(payload["sub"]),
            token_type=token_type,
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    )


async def logout(session: AsyncSession, *, access_token: str, refresh_token: str | None) -> None:
    """Revoke the caller's tokens so they stop working before they expire."""
    access_payload = decode_token(access_token, expected_type="access")
    await _revoke(session, access_payload, "access")

    if refresh_token:
        try:
            refresh_payload = decode_token(refresh_token, expected_type="refresh")
        except AuthenticationError:
            # An expired or malformed refresh token is already unusable, and the
            # access token has been revoked either way. Failing the whole logout
            # here would leave the caller *more* logged in for complaining about
            # a token that could not have been used anyway.
            refresh_payload = None
        if refresh_payload is not None:
            await _revoke(session, refresh_payload, "refresh")

    await session.commit()
    logger.info("logout", extra={"staff_user_id": int(access_payload["sub"])})


async def purge_expired_revocations(session: AsyncSession) -> int:
    """Drop revocation rows for tokens that have expired on their own.

    Past its exp a token is refused by decode_token regardless, so the row stops
    carrying information and is only cost.
    """
    result = await session.execute(
        delete(RevokedToken).where(RevokedToken.expires_at < datetime.now(UTC))
    )
    await session.commit()
    return result.rowcount or 0


async def refresh_tokens(session: AsyncSession, refresh_token: str) -> TokenPair:
    payload = decode_token(refresh_token, expected_type="refresh")

    if await is_revoked(session, payload.get("jti")):
        raise AuthenticationError("This token has been revoked.")

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

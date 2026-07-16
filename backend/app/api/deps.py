from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError
from app.core.security import decode_token
from app.db.session import get_session
from app.models.enums import StaffRole
from app.models.operations import StaffUser
from app.services import auth as auth_service

# auto_error=False so a missing header raises our AuthenticationError (401 with
# our error envelope) rather than FastAPI's default 403.
_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_access_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """The raw bearer string, for endpoints that must act on the token itself."""
    if credentials is None:
        raise AuthenticationError("Missing bearer token.")
    return credentials.credentials


AccessToken = Annotated[str, Depends(get_access_token)]


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> StaffUser:
    if credentials is None:
        raise AuthenticationError("Missing bearer token.")

    payload = decode_token(credentials.credentials, expected_type="access")

    # A valid signature is not the same as a token we still honour. Without this
    # lookup, logout would only be a suggestion: the token stays cryptographically
    # valid until it expires, so a copy of it keeps working.
    if await auth_service.is_revoked(session, payload.get("jti")):
        raise AuthenticationError("This token has been revoked.")

    return await auth_service.get_active_user(session, int(payload["sub"]))


CurrentUser = Annotated[StaffUser, Depends(get_current_user)]


def require_roles(*roles: StaffRole) -> Callable[[StaffUser], StaffUser]:
    """Dependency factory guarding an endpoint behind one or more roles.

    Admin always passes; see auth_service.ensure_role.
    """

    async def _guard(user: CurrentUser) -> StaffUser:
        auth_service.ensure_role(user, set(roles))
        return user

    return _guard


RequireAdmin = Annotated[StaffUser, Depends(require_roles(StaffRole.ADMIN))]
RequireOps = Annotated[StaffUser, Depends(require_roles(StaffRole.OPS))]
RequireCheckin = Annotated[StaffUser, Depends(require_roles(StaffRole.CHECKIN))]
RequireSecurity = Annotated[StaffUser, Depends(require_roles(StaffRole.SECURITY))]

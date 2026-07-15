"""Domain exceptions and their HTTP translation.

The service layer raises these; it never imports FastAPI. Keeping the
translation in one place means business rules stay testable without a
request/response cycle.
"""

from typing import Any


class DomainError(Exception):
    """Base class for expected, client-visible failures."""

    status_code: int = 400
    code: str = "domain_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    """The request is well-formed but collides with existing state."""

    status_code = 409
    code = "conflict"


class ValidationError(DomainError):
    status_code = 422
    code = "validation_error"


class AuthenticationError(DomainError):
    status_code = 401
    code = "authentication_failed"


class PermissionDeniedError(DomainError):
    status_code = 403
    code = "permission_denied"


class IllegalStateTransitionError(ConflictError):
    """A state machine rejected the requested transition."""

    code = "illegal_state_transition"

    def __init__(self, entity: str, current: str, requested: str, allowed: list[str]) -> None:
        super().__init__(
            f"Cannot move {entity} from {current!r} to {requested!r}.",
            details={"current": current, "requested": requested, "allowed": allowed},
        )

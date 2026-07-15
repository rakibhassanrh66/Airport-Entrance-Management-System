from fastapi import APIRouter, status

from app.api.deps import CurrentUser, RequireAdmin, SessionDep
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    StaffUserCreate,
    StaffUserOut,
    TokenPair,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair, summary="Exchange credentials for tokens")
async def login(payload: LoginRequest, session: SessionDep) -> TokenPair:
    user = await auth_service.authenticate(session, payload.email, payload.password)
    return auth_service.issue_tokens(user)


@router.post("/refresh", response_model=TokenPair, summary="Exchange a refresh token")
async def refresh(payload: RefreshRequest, session: SessionDep) -> TokenPair:
    return await auth_service.refresh_tokens(session, payload.refresh_token)


@router.get("/me", response_model=StaffUserOut, summary="The current staff user")
async def me(user: CurrentUser) -> StaffUserOut:
    return StaffUserOut.model_validate(user)


@router.post(
    "/staff",
    response_model=StaffUserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a staff user (admin only)",
)
async def create_staff(
    payload: StaffUserCreate,
    session: SessionDep,
    _: RequireAdmin,
) -> StaffUserOut:
    user = await auth_service.create_staff_user(session, payload)
    return StaffUserOut.model_validate(user)

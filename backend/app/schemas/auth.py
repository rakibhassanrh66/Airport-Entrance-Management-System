from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import StaffRole
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds.")


class RefreshRequest(BaseModel):
    refresh_token: str


class StaffUserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=150)
    # Long enough to resist offline guessing; length beats character-class rules.
    password: str = Field(min_length=12, max_length=128)
    role: StaffRole


class StaffUserOut(ORMModel):
    id: int
    email: str
    full_name: str
    role: StaffRole
    is_active: bool
    last_login_at: datetime | None

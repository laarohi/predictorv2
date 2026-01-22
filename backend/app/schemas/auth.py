"""Authentication schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import AuthProvider


class UserCreate(BaseModel):
    """Schema for user registration."""

    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=100)


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr
    password: str


class UserRead(BaseModel):
    """Schema for reading user data."""

    id: uuid.UUID
    email: str
    name: str
    auth_provider: AuthProvider
    is_admin: bool
    is_active: bool
    competition_id: uuid.UUID | None
    created_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None


class Token(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str  # User ID
    exp: datetime


class GoogleAuthCallback(BaseModel):
    """Google OAuth callback data."""

    code: str
    state: str | None = None

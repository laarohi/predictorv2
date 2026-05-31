"""FastAPI dependencies for auth and database."""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_settings
from app.database import get_session
from app.models._datetime import utc_now
from app.models.user import User
from app.schemas.auth import TokenPayload

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


def create_access_token(
    user_id: str,
    expires_delta: timedelta | None = None,
    token_version: int = 0,
) -> str:
    """Create a JWT access token.

    `token_version` is embedded as the `tv` claim and compared to the user's
    current token_version on every request, so bumping a user's token_version
    invalidates all their outstanding tokens.
    """
    settings = get_settings()
    if expires_delta:
        expire = utc_now() + expires_delta
    else:
        expire = utc_now() + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    to_encode = {"sub": user_id, "exp": expire, "tv": token_version}
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    """Get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token is None:
        raise credentials_exception

    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = TokenPayload(sub=user_id, exp=payload.get("exp"))
    except JWTError:
        raise credentials_exception

    result = await session.execute(select(User).where(User.id == token_data.sub))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    # Reject tokens whose version is stale (user did a sign-out-everywhere /
    # had sessions revoked). Default 0 keeps pre-existing tokens valid.
    if payload.get("tv", 0) != user.token_version:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    return user


async def get_current_user_optional(
    session: Annotated[AsyncSession, Depends(get_session)],
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User | None:
    """Get the current user if authenticated, None otherwise."""
    if token is None:
        return None

    try:
        return await get_current_user(session, token)
    except HTTPException:
        return None


async def get_admin_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require admin user."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# Type aliases for cleaner route signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
AdminUser = Annotated[User, Depends(get_admin_user)]
DbSession = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Per-request metadata captured for prediction-history rows.

    Built fresh on every HTTP request by `get_request_context`. Pass it
    into `app.services.prediction_history.record_*` calls so that audit
    rows record who, where from, and which logical request.
    """

    request_id: uuid.UUID
    client_ip: str | None
    user_agent: str | None


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP, X-Forwarded-For aware.

    When the app sits behind a reverse proxy (production: Cloudflare
    Tunnel → nginx → backend), `request.client.host` is the proxy. The
    leftmost entry in `X-Forwarded-For` is the original client. Only
    trust this header when running behind a known proxy.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def get_request_context(request: Request) -> RequestContext:
    """Build per-request audit metadata."""
    return RequestContext(
        request_id=uuid.uuid4(),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


RequestCtx = Annotated[RequestContext, Depends(get_request_context)]

"""Authentication API routes."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi_sso.sso.google import GoogleSSO
from sqlalchemy import func
from sqlmodel import select

from app.config import get_settings
from app.dependencies import (
    CurrentUser,
    DbSession,
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.models.prediction import MatchPrediction, TeamPrediction
from app.models.user import AuthProvider, User
from app.schemas.auth import PasswordChange, Token, UserCreate, UserLogin, UserRead, UserStats
from app.services.leaderboard import calculate_leaderboard
from app.services.scoring import calculate_user_points

router = APIRouter()


def get_google_sso() -> GoogleSSO:
    """Get Google SSO instance."""
    settings = get_settings()
    return GoogleSSO(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
        allow_insecure_http=settings.debug,
    )


@router.post("/register", response_model=Token)
async def register(user_data: UserCreate, session: DbSession) -> Token:
    """Register a new user with email/password."""
    # Check if email already exists
    result = await session.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=user_data.email,
        name=user_data.name,
        password_hash=get_password_hash(user_data.password),
        auth_provider=AuthProvider.EMAIL,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Generate token
    access_token = create_access_token(
        user_id=str(user.id),
        expires_delta=timedelta(minutes=get_settings().jwt_access_token_expire_minutes),
    )

    return Token(access_token=access_token)


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, session: DbSession) -> Token:
    """Login with email/password."""
    result = await session.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    access_token = create_access_token(
        user_id=str(user.id),
        expires_delta=timedelta(minutes=get_settings().jwt_access_token_expire_minutes),
    )

    return Token(access_token=access_token)


@router.get("/google")
async def google_login():
    """Initiate Google OAuth login."""
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured",
        )

    google_sso = get_google_sso()
    return await google_sso.get_login_redirect()


@router.get("/google/callback")
async def google_callback(request: Request, session: DbSession):
    """Handle Google OAuth callback."""
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured",
        )

    google_sso = get_google_sso()

    try:
        google_user = await google_sso.verify_and_process(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to authenticate with Google: {e}",
        )

    if not google_user or not google_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to get user info from Google",
        )

    # Check if user exists by Google ID
    result = await session.execute(select(User).where(User.google_id == google_user.id))
    user = result.scalar_one_or_none()

    if not user:
        # Check if email exists (link accounts)
        result = await session.execute(select(User).where(User.email == google_user.email))
        user = result.scalar_one_or_none()

        if user:
            # Link Google account to existing user
            user.google_id = google_user.id
            user.auth_provider = AuthProvider.GOOGLE
        else:
            # Create new user
            user = User(
                email=google_user.email,
                name=google_user.display_name or google_user.email.split("@")[0],
                google_id=google_user.id,
                auth_provider=AuthProvider.GOOGLE,
            )
            session.add(user)

        await session.commit()
        await session.refresh(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    # Generate token
    access_token = create_access_token(
        user_id=str(user.id),
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )

    # Redirect to frontend with token
    frontend_url = settings.cors_origins[0] if settings.cors_origins else "http://localhost:5173"
    return RedirectResponse(url=f"{frontend_url}/auth/callback?token={access_token}")


@router.get("/me", response_model=UserRead)
async def get_current_user_info(current_user: CurrentUser) -> UserRead:
    """Get current user information."""
    return UserRead.model_validate(current_user)


@router.post("/me/password")
async def change_password(
    data: PasswordChange, current_user: CurrentUser, session: DbSession
) -> dict[str, str]:
    """Change password for email-authenticated users."""
    if current_user.auth_provider != AuthProvider.EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change is only available for email accounts",
        )

    if not current_user.password_hash or not verify_password(
        data.current_password, current_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.password_hash = get_password_hash(data.new_password)
    session.add(current_user)
    await session.commit()

    return {"message": "Password updated successfully"}


@router.get("/me/stats", response_model=UserStats)
async def get_user_stats(current_user: CurrentUser, session: DbSession) -> UserStats:
    """Get profile statistics for the current user."""
    # Calculate points breakdown
    breakdown = await calculate_user_points(session, current_user.id)

    # Get leaderboard position
    leaderboard = await calculate_leaderboard(session)
    position = None
    for entry in leaderboard.entries:
        if entry.user_id == current_user.id:
            position = entry.position
            break

    # Count raw predictions
    match_count_result = await session.execute(
        select(func.count(MatchPrediction.id)).where(
            MatchPrediction.user_id == current_user.id
        )
    )
    total_match_predictions = match_count_result.scalar_one()

    team_count_result = await session.execute(
        select(func.count(TeamPrediction.id)).where(
            TeamPrediction.user_id == current_user.id
        )
    )
    total_team_predictions = team_count_result.scalar_one()

    total_predictions = total_match_predictions + total_team_predictions

    # Accuracy: correct outcomes / scored match predictions
    accuracy_pct = 0.0
    if breakdown.total_predictions > 0:
        accuracy_pct = round(
            (breakdown.correct_outcomes / breakdown.total_predictions) * 100, 1
        )

    return UserStats(
        total_match_predictions=total_match_predictions,
        total_team_predictions=total_team_predictions,
        total_predictions=total_predictions,
        correct_outcomes=breakdown.correct_outcomes,
        exact_scores=breakdown.exact_scores,
        accuracy_pct=accuracy_pct,
        total_points=breakdown.total,
        leaderboard_position=position,
        total_participants=leaderboard.total_participants,
        breakdown=breakdown,
    )

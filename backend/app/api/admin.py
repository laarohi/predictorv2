"""Admin API routes for dashboard and management."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from app.dependencies import AdminUser, DbSession
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction
from app.models.score import Score, ScoreSource
from app.models.user import User
from app.services.external_scores import get_score_provider, ExternalScore
from app.services.leaderboard import invalidate_cache
from app.services.score_sync import sync_scores_once


router = APIRouter()


class AdminStats(BaseModel):
    """Admin dashboard statistics."""

    total_users: int
    active_users: int
    total_fixtures: int
    completed_fixtures: int
    live_fixtures: int
    total_predictions: int
    total_scores: int


class UserAdminView(BaseModel):
    """User data for admin view."""

    id: uuid.UUID
    email: str
    name: str
    auth_provider: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    prediction_count: int

    class Config:
        """Pydantic config."""

        from_attributes = True


class CompetitionAdminView(BaseModel):
    """Competition data for admin view."""

    id: uuid.UUID
    name: str
    entry_fee: float
    phase1_deadline: datetime | None
    is_phase2_active: bool
    phase2_activated_at: datetime | None
    phase2_bracket_deadline: datetime | None
    phase2_deadline: datetime | None
    is_active: bool
    fixture_count: int
    user_count: int

    class Config:
        """Pydantic config."""

        from_attributes = True


class Phase1DeadlineRequest(BaseModel):
    """Request to set Phase 1 deadline."""

    deadline: datetime  # When Phase 1 predictions lock


class Phase2ActivateRequest(BaseModel):
    """Request to activate Phase 2."""

    bracket_deadline: datetime  # When Phase 2 bracket predictions lock


@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(
    session: DbSession,
    _admin: AdminUser,
) -> AdminStats:
    """Get admin dashboard statistics."""
    # User counts
    total_users = await session.scalar(select(func.count(User.id)))
    active_users = await session.scalar(
        select(func.count(User.id)).where(User.is_active == True)
    )

    # Fixture counts
    total_fixtures = await session.scalar(select(func.count(Fixture.id)))
    completed_fixtures = await session.scalar(
        select(func.count(Fixture.id)).where(Fixture.status == MatchStatus.FINISHED)
    )
    live_fixtures = await session.scalar(
        select(func.count(Fixture.id)).where(
            Fixture.status.in_([MatchStatus.LIVE, MatchStatus.HALFTIME])
        )
    )

    # Prediction and score counts
    total_predictions = await session.scalar(select(func.count(MatchPrediction.id)))
    total_scores = await session.scalar(select(func.count(Score.id)))

    return AdminStats(
        total_users=total_users or 0,
        active_users=active_users or 0,
        total_fixtures=total_fixtures or 0,
        completed_fixtures=completed_fixtures or 0,
        live_fixtures=live_fixtures or 0,
        total_predictions=total_predictions or 0,
        total_scores=total_scores or 0,
    )


@router.get("/users", response_model=list[UserAdminView])
async def get_all_users(
    session: DbSession,
    _admin: AdminUser,
) -> list[UserAdminView]:
    """Get all users with prediction counts (admin only)."""
    # Get users with prediction counts
    result = await session.execute(
        select(
            User,
            func.count(MatchPrediction.id).label("prediction_count")
        )
        .outerjoin(MatchPrediction, User.id == MatchPrediction.user_id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
    )
    rows = result.all()

    return [
        UserAdminView(
            id=user.id,
            email=user.email,
            name=user.name,
            auth_provider=user.auth_provider.value,
            is_admin=user.is_admin,
            is_active=user.is_active,
            created_at=user.created_at,
            prediction_count=count,
        )
        for user, count in rows
    ]


@router.patch("/users/{user_id}/admin", response_model=UserAdminView)
async def toggle_user_admin(
    user_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> UserAdminView:
    """Toggle admin status for a user (admin only)."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_admin = not user.is_admin
    user.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)

    # Get prediction count
    count = await session.scalar(
        select(func.count(MatchPrediction.id)).where(MatchPrediction.user_id == user_id)
    )

    return UserAdminView(
        id=user.id,
        email=user.email,
        name=user.name,
        auth_provider=user.auth_provider.value,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        prediction_count=count or 0,
    )


@router.patch("/users/{user_id}/active", response_model=UserAdminView)
async def toggle_user_active(
    user_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> UserAdminView:
    """Toggle active status for a user (admin only)."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = not user.is_active
    user.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)

    # Get prediction count
    count = await session.scalar(
        select(func.count(MatchPrediction.id)).where(MatchPrediction.user_id == user_id)
    )

    return UserAdminView(
        id=user.id,
        email=user.email,
        name=user.name,
        auth_provider=user.auth_provider.value,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        prediction_count=count or 0,
    )


@router.get("/competitions", response_model=list[CompetitionAdminView])
async def get_all_competitions(
    session: DbSession,
    _admin: AdminUser,
) -> list[CompetitionAdminView]:
    """Get all competitions with stats (admin only)."""
    result = await session.execute(
        select(
            Competition,
            func.count(func.distinct(Fixture.id)).label("fixture_count"),
            func.count(func.distinct(User.id)).label("user_count"),
        )
        .outerjoin(Fixture, Competition.id == Fixture.competition_id)
        .outerjoin(User, Competition.id == User.competition_id)
        .group_by(Competition.id)
        .order_by(Competition.created_at.desc())
    )
    rows = result.all()

    return [
        CompetitionAdminView(
            id=comp.id,
            name=comp.name,
            entry_fee=float(comp.entry_fee),
            phase1_deadline=comp.phase1_deadline,
            is_phase2_active=comp.is_phase2_active,
            phase2_activated_at=comp.phase2_activated_at,
            phase2_bracket_deadline=comp.phase2_bracket_deadline,
            phase2_deadline=comp.phase2_deadline,
            is_active=comp.is_active,
            fixture_count=fixture_count,
            user_count=user_count,
        )
        for comp, fixture_count, user_count in rows
    ]


@router.post("/competition/phase2/activate")
async def activate_phase2(
    request: Phase2ActivateRequest,
    session: DbSession,
    _admin: AdminUser,
) -> dict:
    """Activate Phase 2 for the active competition.

    This enables the Phase 2 tab for all users and sets the bracket deadline.
    """
    # Get active competition
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    competition = result.scalar_one_or_none()

    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found"
        )

    if competition.is_phase2_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phase 2 is already active"
        )

    # Activate Phase 2
    competition.is_phase2_active = True
    competition.phase2_activated_at = datetime.utcnow()
    # Convert to timezone-naive datetime (database uses TIMESTAMP WITHOUT TIME ZONE)
    bracket_deadline = request.bracket_deadline
    if bracket_deadline.tzinfo is not None:
        bracket_deadline = bracket_deadline.replace(tzinfo=None)
    competition.phase2_bracket_deadline = bracket_deadline
    competition.updated_at = datetime.utcnow()

    await session.commit()

    return {
        "status": "Phase 2 activated",
        "bracket_deadline": request.bracket_deadline.isoformat(),
        "activated_at": competition.phase2_activated_at.isoformat(),
    }


@router.post("/competition/phase2/deactivate")
async def deactivate_phase2(
    session: DbSession,
    _admin: AdminUser,
) -> dict:
    """Deactivate Phase 2 for the active competition.

    This hides the Phase 2 tab. Useful for testing or rollback.
    """
    # Get active competition
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    competition = result.scalar_one_or_none()

    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found"
        )

    if not competition.is_phase2_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phase 2 is not active"
        )

    # Deactivate Phase 2
    competition.is_phase2_active = False
    competition.updated_at = datetime.utcnow()

    await session.commit()

    return {"status": "Phase 2 deactivated"}


@router.post("/competition/phase1/deadline")
async def set_phase1_deadline(
    request: Phase1DeadlineRequest,
    session: DbSession,
    _admin: AdminUser,
) -> dict:
    """Set the Phase 1 deadline for the active competition.

    This sets when group stage predictions lock.
    """
    # Get active competition
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    competition = result.scalar_one_or_none()

    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found"
        )

    # Convert to timezone-naive datetime (database uses TIMESTAMP WITHOUT TIME ZONE)
    deadline = request.deadline
    if deadline.tzinfo is not None:
        deadline = deadline.replace(tzinfo=None)

    competition.phase1_deadline = deadline
    competition.updated_at = datetime.utcnow()

    await session.commit()

    return {
        "status": "Phase 1 deadline set",
        "deadline": request.deadline.isoformat(),
    }


class SyncScoresResponse(BaseModel):
    """Response from score sync operation."""

    synced: int
    updated: int
    errors: list[str]


@router.post("/scores/sync", response_model=SyncScoresResponse)
async def sync_scores_from_api(
    session: DbSession,
    _admin: AdminUser,
) -> SyncScoresResponse:
    """Sync live scores from external API (admin only).

    Thin wrapper around `score_sync.sync_scores_once`. The same code path
    powers the background scheduler — this endpoint is the manual escape
    hatch.
    """
    result = await sync_scores_once(session)
    return SyncScoresResponse(
        synced=result.synced,
        updated=result.updated,
        errors=result.errors,
    )

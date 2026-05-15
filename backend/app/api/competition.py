"""Competition API routes."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from app.dependencies import CurrentUser, DbSession
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.user import User
from app.services.locking import get_current_phase, is_phase2_bracket_locked


router = APIRouter()


class CompetitionInfo(BaseModel):
    """Public competition info for the rules / landing pages."""

    name: str
    entry_fee: float
    is_phase2_active: bool
    phase1_deadline: datetime | None
    phase2_bracket_deadline: datetime | None
    total_players: int
    paid_players: int


@router.get("/info", response_model=CompetitionInfo)
async def get_competition_info(session: DbSession) -> CompetitionInfo:
    """Public competition metadata — no auth required so the /rules page
    works for prospective joiners. Returns tournament name, entry fee,
    deadlines, current phase, and player counts."""
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    if not competition:
        return CompetitionInfo(
            name="World Cup 2026",
            entry_fee=0.0,
            is_phase2_active=False,
            phase1_deadline=None,
            phase2_bracket_deadline=None,
            total_players=0,
            paid_players=0,
        )

    total = await session.scalar(
        select(func.count(User.id)).where(User.is_active == True)  # noqa: E712
    )
    paid = await session.scalar(
        select(func.count(User.id))
        .where(User.is_active == True)  # noqa: E712
        .where(User.paid == True)  # noqa: E712
    )

    return CompetitionInfo(
        name=competition.name,
        entry_fee=float(competition.entry_fee),
        is_phase2_active=competition.is_phase2_active,
        phase1_deadline=competition.phase1_deadline,
        phase2_bracket_deadline=competition.phase2_bracket_deadline,
        total_players=total or 0,
        paid_players=paid or 0,
    )


class PhaseStatus(BaseModel):
    """Current phase status for frontend."""

    current_phase: str  # 'phase_1' or 'phase_2'
    # Phase 1
    phase1_deadline: datetime | None
    phase1_locked: bool
    # Phase 2
    is_phase2_active: bool
    phase2_bracket_deadline: datetime | None
    phase2_bracket_locked: bool


@router.get("/phase-status", response_model=PhaseStatus)
async def get_phase_status(
    session: DbSession,
    _current_user: CurrentUser,
) -> PhaseStatus:
    """Get current phase status for the active competition.

    This endpoint allows the frontend to determine:
    - Phase 1 deadline and lock status
    - Whether to show the Phase 2 tab
    - Whether the Phase 2 bracket is locked
    - The Phase 2 bracket deadline
    """
    # Get active competition
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    competition = result.scalar_one_or_none()

    current_phase = await get_current_phase(session)
    bracket_locked = await is_phase2_bracket_locked(session)

    # Check if phase 1 is locked (past deadline)
    phase1_locked = False
    if competition and competition.phase1_deadline:
        phase1_locked = utc_now() >= competition.phase1_deadline

    return PhaseStatus(
        current_phase=current_phase.value,
        phase1_deadline=competition.phase1_deadline if competition else None,
        phase1_locked=phase1_locked,
        is_phase2_active=competition.is_phase2_active if competition else False,
        phase2_bracket_deadline=competition.phase2_bracket_deadline if competition else None,
        phase2_bracket_locked=bracket_locked,
    )

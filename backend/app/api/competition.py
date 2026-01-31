"""Competition API routes."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import select

from app.dependencies import CurrentUser, DbSession
from app.models.competition import Competition
from app.services.locking import get_current_phase, is_phase2_bracket_locked


router = APIRouter()


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
        phase1_locked = datetime.utcnow() >= competition.phase1_deadline

    return PhaseStatus(
        current_phase=current_phase.value,
        phase1_deadline=competition.phase1_deadline if competition else None,
        phase1_locked=phase1_locked,
        is_phase2_active=competition.is_phase2_active if competition else False,
        phase2_bracket_deadline=competition.phase2_bracket_deadline if competition else None,
        phase2_bracket_locked=bracket_locked,
    )

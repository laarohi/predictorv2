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
from app.services.locking import (
    get_current_phase,
    is_phase1_locked,
    is_phase2_bracket_locked,
)
from app.config import get_tournament_config
from app.services.scoring import get_scoring_config


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

    # YAML is the source of truth for entry_fee — the dashboard payment
    # banner reads this value to render copy AND to build the Revolut URL.
    # The DB column stays as a fallback so the admin's "update competition"
    # form keeps working without a migration.
    yaml_fee = get_tournament_config().get("tournament", {}).get("entry_fee")
    entry_fee = float(yaml_fee) if yaml_fee is not None else float(competition.entry_fee)

    return CompetitionInfo(
        name=competition.name,
        entry_fee=entry_fee,
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

    # Check if phase 1 is locked (past deadline) — single source of truth
    # in the locking service, same rule the write endpoints enforce.
    phase1_locked = await is_phase1_locked(session)

    return PhaseStatus(
        current_phase=current_phase.value,
        phase1_deadline=competition.phase1_deadline if competition else None,
        phase1_locked=phase1_locked,
        is_phase2_active=competition.is_phase2_active if competition else False,
        phase2_bracket_deadline=competition.phase2_bracket_deadline if competition else None,
        phase2_bracket_locked=bracket_locked,
    )


class ScoringConfigResponse(BaseModel):
    """Scoring configuration as the frontend needs it to render per-match
    breakdowns (Outcome / Exact / Rarity pills + Total) and the public /rules
    page bracket-points table.

    The rarity formula uses per-fixture predictor counts, not a global
    player count — the frontend has those via `/predictions/agreements`
    (FixtureAgreement.total). For mode='logarithmic':

        R = min(rarity_cap, round(alpha * log2(1 / (2f))))

    where f = agrees_outcome / total and alpha = 10/log2(15) ≈ 2.5596.

    Advancement points are split by phase: `advancement` is the Phase 1
    per-round table (round_of_32 … winner), `advancement_phase2` the Phase 2
    table, and `group_position` the Phase 1 group-position bonus. The /rules
    page renders both as a single round × phase table.
    """

    mode: str  # 'fixed' | 'hybrid' (legacy) | 'logarithmic'
    outcome_points: int
    exact_points: int
    rarity_cap: int
    group_position: int
    advancement: dict[str, int]
    advancement_phase2: dict[str, int]


@router.get("/scoring-config", response_model=ScoringConfigResponse)
async def get_scoring_config_endpoint() -> ScoringConfigResponse:
    """Return scoring config so the Results & Fixtures page can project
    per-match rarity bonuses client-side using the same formula the backend
    will eventually score with, and the public /rules page can render the
    bracket-points table. Per-fixture predictor counts come from
    /predictions/agreements.

    Public (no auth) — scoring rules are the published content of the /rules
    page, which prospective joiners read before signing up. Mirrors the public
    posture of /info."""
    config = get_scoring_config()
    match_cfg = config.get("match", {})
    adv = config.get("advancement", {})
    # Split the advancement block into its Phase 1 round table, the nested
    # Phase 2 table, and the standalone group-position bonus. The round keys
    # (round_of_32 … winner) are everything except the two non-round entries.
    phase2 = adv.get("phase_2", {})
    advancement = {
        k: v
        for k, v in adv.items()
        if k not in ("group_position", "phase_2") and isinstance(v, int)
    }
    return ScoringConfigResponse(
        mode=config.get("mode", "logarithmic"),
        outcome_points=match_cfg.get("correct_outcome", 5),
        exact_points=match_cfg.get("exact_score", 10),
        rarity_cap=match_cfg.get("rarity_cap", match_cfg.get("hybrid_cap", 10)),
        group_position=adv.get("group_position", 5),
        advancement=advancement,
        advancement_phase2={k: v for k, v in phase2.items() if isinstance(v, int)},
    )

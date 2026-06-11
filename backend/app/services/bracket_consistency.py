"""Server-side consistency validation for Phase 1 bracket submissions.

A Phase 1 bracket is derived from the user's *predicted* group standings:
the R32 line-up must be the 32 teams those standings send through (top 2
per group + 8 best thirds), and every later-round pick must descend from
the rounds before it. The frontend reconciles this on save
(`frontend/src/lib/utils/bracketReconcile.ts`); this module is the
defense-in-depth layer that stops a stale or buggy client from persisting
knockout rows that contradict the user's saved group predictions.

Two independent checks:

1. Stage-chain (payload-internal, always enforced for Phase 1): each
   stage's teams must appear in the previous stage. Pairing-level slot
   validation is intentionally NOT replicated here — that requires the
   FIFA bracket template, which lives frontend-side; the chain + roster
   checks bound the damage a divergent client can do.

2. R32 roster (enforced only when the user's saved Phase 1 group
   predictions are complete): every submitted ``round_of_32`` team must
   be a qualifier under the standings those predictions imply. Derived
   with the same Article 13 chain the frontend uses (parity-locked by
   the golden standings tests).

Phase 2 brackets are exempt: their line-up comes from actual results and
the payload legitimately starts at the round of 16.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase
from app.schemas.prediction import TeamAdvancementPrediction

# (stage, stage it must descend from) — payload stage names are singular.
_STAGE_CHAIN: list[tuple[str, str]] = [
    ("round_of_16", "round_of_32"),
    ("quarter_final", "round_of_16"),
    ("semi_final", "quarter_final"),
    ("final", "semi_final"),
    ("winner", "final"),
]


def check_stage_chain(predictions: list[TeamAdvancementPrediction]) -> list[str]:
    """Every pick must descend from the previous stage. Pure, no I/O."""
    by_stage: dict[str, set[str]] = {}
    for p in predictions:
        by_stage.setdefault(p.stage, set()).add(p.team)

    problems: list[str] = []
    for stage, prev in _STAGE_CHAIN:
        orphans = sorted(by_stage.get(stage, set()) - by_stage.get(prev, set()))
        if orphans:
            problems.append(
                f"'{stage}' picks missing from '{prev}': {', '.join(orphans)}"
            )
    return problems


async def get_predicted_qualifiers(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> set[str] | None:
    """The 32 teams the user's predicted standings send to the R32.

    Returns ``None`` when the user's Phase 1 group predictions are
    incomplete — qualifiers can't be derived from partial standings, and
    the caller must then skip roster validation rather than reject.
    """
    total_group_fixtures = (
        await session.execute(
            select(func.count()).select_from(Fixture).where(Fixture.stage == "group")
        )
    ).scalar_one()
    predicted_count = (
        await session.execute(
            select(func.count())
            .select_from(MatchPrediction)
            .join(Fixture, Fixture.id == MatchPrediction.fixture_id)
            .where(
                MatchPrediction.user_id == user_id,
                MatchPrediction.phase == PredictionPhase.PHASE_1,
                Fixture.stage == "group",
            )
        )
    ).scalar_one()
    if total_group_fixtures == 0 or predicted_count < total_group_fixtures:
        return None

    # Imported here to mirror scoring.py — standings pulls MatchPrediction
    # into the import chain and is imported from many places.
    from app.services.standings import (
        _apply_fifa_tiebreakers,
        _resolve_fifa_rankings,
        get_predicted_group_standings,
    )

    standings, _warnings = await get_predicted_group_standings(session, user_id)

    qualifiers: set[str] = set()
    thirds: list[dict] = []
    for group, teams in standings.items():
        if len(teams) < 4:
            # Defensive: complete predictions should always rank 4 teams.
            return None
        qualifiers.add(teams[0]["team"])
        qualifiers.add(teams[1]["team"])
        thirds.append({**teams[2], "group": group})

    rankings = await _resolve_fifa_rankings(session)
    sorted_thirds, _third_warnings = _apply_fifa_tiebreakers(
        thirds,
        group_matches=None,  # H2H not applicable cross-group
        context="third_place_qualifying",
        fifa_rankings=rankings,
    )
    qualifiers.update(t["team"] for t in sorted_thirds[:8])
    return qualifiers


async def validate_phase1_bracket(
    session: AsyncSession,
    user_id: uuid.UUID,
    predictions: list[TeamAdvancementPrediction],
) -> list[str]:
    """All Phase 1 consistency problems with this payload ([] = valid)."""
    problems = check_stage_chain(predictions)

    qualifiers = await get_predicted_qualifiers(session, user_id)
    if qualifiers is not None:
        r32 = sorted({p.team for p in predictions if p.stage == "round_of_32"})
        stale = [t for t in r32 if t not in qualifiers]
        if stale:
            problems.append(
                "'round_of_32' contains teams that do not qualify under your "
                f"current group predictions: {', '.join(stale)}"
            )
    return problems

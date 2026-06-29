"""Ghost entrants' PHASE-2 (knockout) predictions — lock-aware, recurring-safe.

Companion to seed_ghosts.py (frozen Phase-1 set). PHASE-2 ONLY: never touches
the ghosts' locked Phase-1 rows.

Two operations, two cadences:

  brackets  — ONE-TIME. The Phase-2 bracket re-pick (R16→winner) seeded from the
              ACTUAL group standings, advancing the more-supported team per node
              (market reach-odds for polymarket, pool consensus for crowd).
              Refuses to rebuild once the Phase-2 bracket is locked, so a stray
              re-run can't silently re-pick a frozen bracket.

  matches   — RECURRING (auto-scheduled; safe to re-run every few minutes). KO
              match-score predictions, applied with the rule:
                * fixture the ghost hasn't predicted yet  -> INSERT (this is how
                  already-locked/played games get captured on the first run —
                  the crowd's game-1 pick, polymarket's POLY_BACKFILL).
                * fixture already predicted, still UNLOCKED -> REFRESH (latest
                  pool modal / market snapshot).
                * fixture already predicted, LOCKED -> SKIP (preserve the banked
                  pick — never rewrite a locked prediction).

Polymarket reads the committed scripts/data/polymarket_ko_wc2026.json (regenerate
per round on the analysis machine: refresh_market.py scrape ->
generate_polymarket_ko_snapshot.py -> deploy). Crowd reads the live pool.

Both ghosts must already exist (seed_ghosts.py). Run:
    python -m scripts.seed_ghosts_ko brackets
    python -m scripts.seed_ghosts_ko matches
    python -m scripts.seed_ghosts_ko both
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import delete, select

from app.config import get_settings
from app.models._datetime import utc_now
from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.user import User
from app.services.locking import check_fixture_locked, is_phase2_bracket_locked
from app.services.standings import (
    get_actual_group_standings,
    get_qualifying_third_place_teams,
)

from scripts.ghost_lib import ROUND_ORDER, build_bracket, modal_score

CROWD_EMAIL = "crowd@ghosts.predictor.invalid"
POLY_EMAIL = "polymarket@ghosts.predictor.invalid"
KO_DATA = Path(__file__).parent / "data" / "polymarket_ko_wc2026.json"

# Already-played KO games with no live market — the polymarket ghost's pick set
# by hand, in OUR fixture orientation. "Canada to pass 1-0": Canada is away, so
# 0-1. VERIFY each fixture's home/away on the target DB.
POLY_BACKFILL: dict[tuple[str, str], tuple[int, int]] = {
    ("South Korea", "Canada"): (0, 1),
}

# Bracket re-pick covers R16→winner; R32 is the known actual lineup (0 pts in
# Phase 2, not shown on the journey), so we don't store R32 TeamPredictions.
BRACKET_STAGES = ROUND_ORDER[1:]  # round_of_16 .. winner


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _engine():
    url = str(get_settings().database_url).replace("postgresql://", "postgresql+asyncpg://")
    return create_async_engine(url, echo=False)


async def _ghost(session: AsyncSession, email: str) -> User:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"ghost {email} not found — run seed_ghosts.py first")
    if not user.is_ghost:
        raise SystemExit(f"{email} exists but is_ghost is False — refusing to touch it")
    return user


async def _ko_fixtures(session: AsyncSession) -> list[Fixture]:
    rows = await session.execute(select(Fixture).where(Fixture.stage != "group"))
    return list(rows.scalars().all())


async def _actual_order_and_thirds(session: AsyncSession):
    """ACTUAL group standings + qualifying thirds — the real R32 seed for the
    Phase-2 bracket (Phase 1 seeds from *predicted* standings instead)."""
    standings = await get_actual_group_standings(session)
    order = {g: [row["team"] for row in rows] for g, rows in standings.items()}
    thirds_rows = await get_qualifying_third_place_teams(session)
    thirds = [(t["group"], t["team"]) for t in thirds_rows]
    return order, thirds


async def _existing_match_preds(session: AsyncSession, user_id) -> dict:
    rows = await session.execute(
        select(MatchPrediction).where(
            MatchPrediction.user_id == user_id,
            MatchPrediction.phase == PredictionPhase.PHASE_2,
        )
    )
    return {p.fixture_id: p for p in rows.scalars().all()}


async def _apply_match_picks(
    session: AsyncSession,
    user_id,
    candidates: dict,            # fixture_id -> (home, away)
    fixtures_by_id: dict,        # fixture_id -> Fixture
) -> dict[str, int]:
    """Lock-aware upsert: insert if absent; refresh if present-and-unlocked;
    skip if present-and-locked. Returns counts for logging."""
    existing = await _existing_match_preds(session, user_id)
    now = utc_now()
    inserted = refreshed = preserved = 0
    for fid, (h, a) in candidates.items():
        fx = fixtures_by_id.get(fid)
        if fx is None:
            continue
        if fid not in existing:
            session.add(MatchPrediction(
                user_id=user_id, fixture_id=fid, home_score=h, away_score=a,
                phase=PredictionPhase.PHASE_2, locked_at=now,
            ))
            inserted += 1
        elif not check_fixture_locked(fx):
            await session.execute(
                delete(MatchPrediction).where(
                    MatchPrediction.user_id == user_id,
                    MatchPrediction.fixture_id == fid,
                    MatchPrediction.phase == PredictionPhase.PHASE_2,
                )
            )
            session.add(MatchPrediction(
                user_id=user_id, fixture_id=fid, home_score=h, away_score=a,
                phase=PredictionPhase.PHASE_2, locked_at=now,
            ))
            refreshed += 1
        else:
            preserved += 1
    await session.commit()
    return {"inserted": inserted, "refreshed": refreshed, "preserved": preserved}


async def _rebuild_bracket(session: AsyncSession, user_id, support) -> dict:
    """Wipe + rebuild this ghost's Phase-2 bracket. Caller guards the lock."""
    await session.execute(
        delete(TeamPrediction).where(
            TeamPrediction.user_id == user_id,
            TeamPrediction.phase == PredictionPhase.PHASE_2,
        )
    )
    order, thirds = await _actual_order_and_thirds(session)
    stages = build_bracket(order, thirds, support)
    now = utc_now()
    for s in BRACKET_STAGES:
        for t in stages[s]:
            session.add(TeamPrediction(
                user_id=user_id, team=t, stage=s, group_position=None,
                phase=PredictionPhase.PHASE_2, locked_at=now,
            ))
    await session.commit()
    return stages


# ---------------------------------------------------------------------------
# Support functions (who advances at each bracket node)
# ---------------------------------------------------------------------------


def _polymarket_support(probs: dict[str, dict[str, float]]):
    def support(team: str, stage: str) -> tuple:
        p = probs.get(team, {})
        i = ROUND_ORDER.index(stage)
        chain = [p.get(s, 0.0) for s in ROUND_ORDER[i:]]
        return (p.get(stage, 0.0), sum(chain), -ord(team[0].lower()))
    return support


def _crowd_support(stage_counts: dict[str, dict[str, int]]):
    def support(team: str, stage: str) -> tuple:
        i = ROUND_ORDER.index(stage)
        deeper = sum(stage_counts[s][team] for s in ROUND_ORDER[i + 1:])
        return (
            stage_counts[stage][team],
            deeper,
            stage_counts["round_of_32"][team],
            -ord(team[0].lower()),
        )
    return support


async def _pool_stage_counts(session: AsyncSession) -> dict[str, dict[str, int]]:
    rows = await session.execute(
        select(TeamPrediction.team, TeamPrediction.stage)
        .join(User, TeamPrediction.user_id == User.id)
        .where(TeamPrediction.phase == PredictionPhase.PHASE_2, User.is_ghost == False)  # noqa: E712
    )
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for team, stage in rows.all():
        counts[stage][team] += 1
    return counts


# ---------------------------------------------------------------------------
# Public operations (used by the CLI and the scheduler)
# ---------------------------------------------------------------------------


def _load_ko_snapshot() -> dict | None:
    """The committed Polymarket KO snapshot, or None if it hasn't been
    generated/deployed yet. Returning None (not raising) keeps the recurring
    scheduler job alive — it just skips the polymarket half until a snapshot
    lands."""
    if not KO_DATA.exists():
        return None
    return json.loads(KO_DATA.read_text())


async def refresh_phase2_matches(session: AsyncSession, *, log=print) -> None:
    """RECURRING, lock-aware KO match-score seeding for both ghosts. Safe to
    call on a schedule — never rewrites a locked/banked pick."""
    fixtures = await _ko_fixtures(session)
    by_id = {fx.id: fx for fx in fixtures}
    by_teams = {(fx.home_team, fx.away_team): fx for fx in fixtures}

    # Crowd: modal of the real pool's Phase-2 KO scores.
    crowd = await _ghost(session, CROWD_EMAIL)
    pool_rows = await session.execute(
        select(MatchPrediction)
        .join(User, MatchPrediction.user_id == User.id)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .where(
            MatchPrediction.phase == PredictionPhase.PHASE_2,
            Fixture.stage != "group",
            User.is_ghost == False,  # noqa: E712
        )
    )
    counts: dict = defaultdict(lambda: defaultdict(int))
    for p in pool_rows.scalars().all():
        counts[p.fixture_id][(p.home_score, p.away_score)] += 1
    crowd_picks = {fid: modal_score(dict(c)) for fid, c in counts.items()}
    c = await _apply_match_picks(session, crowd.id, crowd_picks, by_id)
    log(f"crowd KO matches: +{c['inserted']} new, ~{c['refreshed']} refreshed, "
        f"{c['preserved']} locked-preserved")

    # Polymarket: live-market scores from the committed snapshot + backfill.
    data = _load_ko_snapshot()
    if data is None:
        log("polymarket KO matches: no snapshot deployed yet — skipped")
        return
    poly = await _ghost(session, POLY_EMAIL)
    poly_picks: dict = {}
    unmatched = 0
    for row in data["match_scores"]:
        fx = by_teams.get((row["home"], row["away"]))
        if fx is None:
            unmatched += 1
            continue
        poly_picks[fx.id] = (row["score"][0], row["score"][1])
    for (h, a), score in POLY_BACKFILL.items():
        fx = by_teams.get((h, a))
        if fx is not None:
            poly_picks.setdefault(fx.id, score)
    p = await _apply_match_picks(session, poly.id, poly_picks, by_id)
    log(f"polymarket KO matches: +{p['inserted']} new, ~{p['refreshed']} refreshed, "
        f"{p['preserved']} locked-preserved ({unmatched} market matchups not in fixtures)")


async def seed_phase2_brackets(session: AsyncSession, *, force: bool = False, log=print) -> None:
    """ONE-TIME Phase-2 bracket re-pick for both ghosts. Refuses once the
    Phase-2 bracket is locked (pass force=True only if you really mean it)."""
    if await is_phase2_bracket_locked(session) and not force:
        raise SystemExit(
            "Phase-2 bracket is LOCKED — refusing to re-pick the ghosts' brackets "
            "(would edit a frozen prediction). Pass force=True to override."
        )
    data = _load_ko_snapshot()
    if data is None:
        raise SystemExit(f"missing KO snapshot {KO_DATA} — generate it first")
    poly = await _ghost(session, POLY_EMAIL)
    stages = await _rebuild_bracket(session, poly.id, _polymarket_support(data["team_stage_probs"]))
    log(f"polymarket bracket: winner = {stages['winner'][0]}")

    crowd = await _ghost(session, CROWD_EMAIL)
    stages = await _rebuild_bracket(session, crowd.id, _crowd_support(await _pool_stage_counts(session)))
    log(f"crowd bracket: winner = {stages['winner'][0]}")


async def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("brackets", "matches", "both"):
        raise SystemExit(__doc__)
    which = sys.argv[1]
    engine = _engine()
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        if which in ("brackets", "both"):
            await seed_phase2_brackets(session)
        if which in ("matches", "both"):
            await refresh_phase2_matches(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

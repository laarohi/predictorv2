"""Create / refresh the ghost entrants' Phase-1 prediction sets.

Two ghosts (users.is_ghost=True — excluded from every aggregate, see
test_ghost_exclusion.py):

  crowd       "The Crowd"  — the mode answer of the real pool: modal score
              per group match, modal bonus answers, and a bracket built by
              advancing the more-supported team at every node of the real
              FIFA tree (so it is always structurally legal, even when the
              crowd's two favourite finalists sit in the same half).
  polymarket  "Polymarket" — the market's answer, from a pre-tournament
              snapshot JSON (scripts/data/polymarket_wc2026.json, generated
              on the analysis machine from the prediction-model DuckDB +
              the award markets): most-likely exact score per match,
              bracket by market reach-probabilities along the same tree,
              award answers from the market, remaining bonus answers
              derived from its own predicted scores/bracket.

Both ghosts' picks are deterministic functions of locked Phase-1 data /
a frozen market snapshot, so the script is idempotent: rerunning wipes
and reinserts the same rows. Run AFTER Phase 1 locks (the crowd mode is
undefined before, and inserting earlier would leak consensus).

Run:
    docker-compose exec backend python -m scripts.seed_ghosts crowd
    docker-compose exec backend python -m scripts.seed_ghosts polymarket
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import delete, select

from app.config import get_settings
from app.models._datetime import utc_now
from app.models.bonus import BonusPrediction
from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.user import AuthProvider, User
from app.schemas.prediction import TeamAdvancementPrediction
from app.services.bracket_consistency import validate_phase1_bracket

from scripts.ghost_lib import (
    ROUND_ORDER,
    build_bracket,
    derived_dark_horse,
    derived_flop,
    derived_group_goal_answers,
    modal_answer,
    modal_score,
)

CROWD = ("crowd@ghosts.predictor.invalid", "The Crowd")
POLYMARKET = ("polymarket@ghosts.predictor.invalid", "Polymarket")
POLY_DATA = Path(__file__).parent / "data" / "polymarket_wc2026.json"


def _engine():
    url = str(get_settings().database_url).replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    return create_async_engine(url, echo=False)


async def _get_or_create_ghost(session: AsyncSession, email: str, name: str) -> User:
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            name=name,
            is_ghost=True,
            is_active=True,
            password_hash=None,  # cannot log in
            google_id=None,
            auth_provider=AuthProvider.EMAIL,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(f"created ghost user {name} ({user.id})")
    elif not user.is_ghost:
        raise SystemExit(f"{email} exists but is_ghost is False — refusing to touch it")
    return user


async def _wipe_ghost_predictions(session: AsyncSession, user_id) -> None:
    for model in (MatchPrediction, TeamPrediction, BonusPrediction):
        await session.execute(delete(model).where(model.user_id == user_id))
    await session.commit()


async def _group_fixtures(session: AsyncSession) -> list[Fixture]:
    rows = await session.execute(select(Fixture).where(Fixture.stage == "group"))
    return list(rows.scalars().all())


async def _ghost_standings_and_thirds(session: AsyncSession, user_id):
    """The ghost's own predicted standings (from its just-inserted match
    scores) + the 8 qualifying thirds — exactly the derivation
    validate_phase1_bracket checks the R32 roster against."""
    from app.services.standings import (
        _apply_fifa_tiebreakers,
        _resolve_fifa_rankings,
        get_predicted_group_standings,
    )

    standings, _ = await get_predicted_group_standings(session, user_id)
    order = {g: [row["team"] for row in rows] for g, rows in standings.items()}

    thirds = [{**rows[2], "group": g} for g, rows in standings.items()]
    rankings = await _resolve_fifa_rankings(session)
    sorted_thirds, _ = _apply_fifa_tiebreakers(
        thirds, group_matches=None, context="third_place_qualifying",
        fifa_rankings=rankings,
    )
    qualifying = [(t["group"], t["team"]) for t in sorted_thirds[:8]]
    return order, qualifying, rankings


async def _insert_match_predictions(
    session: AsyncSession, user_id, picks: dict, fixtures: list[Fixture]
) -> None:
    now = utc_now()
    for fx in fixtures:
        h, a = picks[fx.id]
        session.add(
            MatchPrediction(
                user_id=user_id, fixture_id=fx.id, home_score=h, away_score=a,
                phase=PredictionPhase.PHASE_1, locked_at=now,
            )
        )
    await session.commit()


async def _insert_bracket(session: AsyncSession, user_id, stages: dict) -> None:
    payload = [
        TeamAdvancementPrediction(team=t, stage=s, group_position=None)
        for s in ROUND_ORDER
        for t in stages[s]
    ]
    problems = await validate_phase1_bracket(session, user_id, payload)
    if problems:
        raise SystemExit(f"ghost bracket failed consistency validation: {problems}")

    now = utc_now()
    for p in payload:
        session.add(
            TeamPrediction(
                user_id=user_id, team=p.team, stage=p.stage, group_position=None,
                phase=PredictionPhase.PHASE_1, locked_at=now,
            )
        )
    await session.commit()


async def _insert_bonus(session: AsyncSession, user_id, answers: dict[str, str]) -> None:
    for qid, answer in answers.items():
        session.add(
            BonusPrediction(user_id=user_id, question_id=qid, answer=answer,
                            phase=PredictionPhase.PHASE_1)
        )
    await session.commit()


# ---------------------------------------------------------------------------
# Crowd ghost
# ---------------------------------------------------------------------------


async def seed_crowd(session: AsyncSession) -> None:
    ghost = await _get_or_create_ghost(session, *CROWD)
    await _wipe_ghost_predictions(session, ghost.id)

    fixtures = await _group_fixtures(session)

    # Modal score per group fixture, real users only.
    pred_rows = await session.execute(
        select(MatchPrediction)
        .join(User, MatchPrediction.user_id == User.id)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .where(
            MatchPrediction.phase == PredictionPhase.PHASE_1,
            Fixture.stage == "group",
            User.is_ghost == False,  # noqa: E712
        )
    )
    counts: dict = defaultdict(lambda: defaultdict(int))
    for p in pred_rows.scalars().all():
        counts[p.fixture_id][(p.home_score, p.away_score)] += 1
    missing = [fx for fx in fixtures if not counts.get(fx.id)]
    if missing:
        raise SystemExit(
            f"{len(missing)} group fixtures have no real predictions — "
            "run after Phase 1 locks with a populated pool"
        )
    picks = {fid: modal_score(dict(c)) for fid, c in counts.items()}
    await _insert_match_predictions(session, ghost.id, picks, fixtures)

    # Bracket: crowd support per (team, stage), real users only.
    tp_rows = await session.execute(
        select(TeamPrediction.team, TeamPrediction.stage)
        .join(User, TeamPrediction.user_id == User.id)
        .where(
            TeamPrediction.phase == PredictionPhase.PHASE_1,
            User.is_ghost == False,  # noqa: E712
        )
    )
    stage_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for team, stage in tp_rows.all():
        stage_counts[stage][team] += 1

    def support(team: str, stage: str) -> tuple:
        i = ROUND_ORDER.index(stage)
        deeper = sum(stage_counts[s][team] for s in ROUND_ORDER[i + 1:])
        # More picks at this stage, then deeper conviction, then overall
        # bracket presence; alphabetical last so ties are deterministic.
        return (
            stage_counts[stage][team],
            deeper,
            stage_counts["round_of_32"][team],
            -ord(team[0].lower()),
        )

    order, qualifying_thirds, _ = await _ghost_standings_and_thirds(session, ghost.id)
    stages = build_bracket(order, qualifying_thirds, support)
    await _insert_bracket(session, ghost.id, stages)

    # Bonus: modal answer per question, real users only.
    bp_rows = await session.execute(
        select(BonusPrediction.question_id, BonusPrediction.answer)
        .join(User, BonusPrediction.user_id == User.id)
        .where(User.is_ghost == False)  # noqa: E712
    )
    answer_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for qid, answer in bp_rows.all():
        if answer:
            answer_counts[qid][answer] += 1
    answers = {qid: modal_answer(dict(c)) for qid, c in answer_counts.items()}
    await _insert_bonus(session, ghost.id, answers)

    print(f"crowd ghost seeded: {len(picks)} scores, 63 bracket rows, "
          f"{len(answers)} bonus answers, winner = {stages['winner'][0]}")


# ---------------------------------------------------------------------------
# Polymarket ghost
# ---------------------------------------------------------------------------


async def seed_polymarket(session: AsyncSession) -> None:
    if not POLY_DATA.exists():
        raise SystemExit(f"missing market snapshot {POLY_DATA} — generate it first")
    data = json.loads(POLY_DATA.read_text())

    ghost = await _get_or_create_ghost(session, *POLYMARKET)
    await _wipe_ghost_predictions(session, ghost.id)

    fixtures = await _group_fixtures(session)
    by_teams = {(fx.home_team, fx.away_team): fx for fx in fixtures}

    picks: dict = {}
    score_by_teams: dict[tuple[str, str], tuple[int, int]] = {}
    for row in data["match_scores"]:
        key = (row["home"], row["away"])
        fx = by_teams.get(key)
        if fx is None:
            raise SystemExit(f"market match {key} not found in fixtures")
        picks[fx.id] = (row["score"][0], row["score"][1])
        score_by_teams[key] = picks[fx.id]
    unmatched = [fx for fx in fixtures if fx.id not in picks]
    if unmatched:
        raise SystemExit(
            f"{len(unmatched)} fixtures missing from the market snapshot, e.g. "
            f"{unmatched[0].home_team} vs {unmatched[0].away_team}"
        )
    await _insert_match_predictions(session, ghost.id, picks, fixtures)

    # Bracket: support = market reach-probability for the stage (champion
    # odds for 'winner'), falling back deeper→shallower so every team has
    # a defined key.
    probs: dict[str, dict[str, float]] = data["team_stage_probs"]

    def support(team: str, stage: str) -> tuple:
        p = probs.get(team, {})
        i = ROUND_ORDER.index(stage)
        chain = [p.get(s, 0.0) for s in ROUND_ORDER[i:]]
        return (p.get(stage, 0.0), sum(chain), -ord(team[0].lower()))

    order, qualifying_thirds, rankings = await _ghost_standings_and_thirds(
        session, ghost.id
    )
    stages = build_bracket(order, qualifying_thirds, support)
    await _insert_bracket(session, ghost.id, stages)

    # Bonus: award answers straight from the market; the rest derived from
    # the ghost's own predicted scores / bracket.
    answers: dict[str, str] = dict(data.get("award_answers", {}))
    answers.update(derived_group_goal_answers(score_by_teams))
    rank_of = {team: i + 1 for i, team in enumerate(rankings)}
    all_teams = sorted({t for pair in score_by_teams for t in pair})
    dark = derived_dark_horse(stages, rank_of)
    flop = derived_flop(all_teams, stages, rank_of)
    if dark:
        answers["dark_horse"] = dark
    if flop:
        answers["flop"] = flop
    await _insert_bonus(session, ghost.id, answers)

    print(f"polymarket ghost seeded: {len(picks)} scores, 63 bracket rows, "
          f"{len(answers)} bonus answers, winner = {stages['winner'][0]}")


async def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("crowd", "polymarket"):
        raise SystemExit(__doc__)
    engine = _engine()
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        if sys.argv[1] == "crowd":
            await seed_crowd(session)
        else:
            await seed_polymarket(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

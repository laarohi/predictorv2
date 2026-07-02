"""Per-user points log — a chronological ledger of every point award.

The scoring engine (`services/scoring.py`) computes AGGREGATES on read;
nothing in the system persists a per-award event. This module re-runs the
same scoring primitives but emits one timestamped `PointsLogEvent` per award
— and, for transparency, per graded MISS — so the frontend can render a
"where did my points come from" timeline.

Reconciliation invariant (locked by tests/test_points_log.py):

    sum(e.points for e in build_points_log(session, user_id))
        == calculate_user_points(session, user_id) total

Every award routes through the exact code the leaderboard uses
(`calculate_match_points`, the per-phase advancement point tables,
the bonus answer matching), so the log cannot drift from the leaderboard.

Timeline anchors — no award carries its own timestamp, so each event is
pinned to the underlying football moment:

- match points             → the fixture's kickoff
- R32 qualification (+10) and group-position bonus (+5)
                           → the last kickoff of the team's group
                             (3rd-place fates: the last kickoff of the whole
                             group stage — best-8-thirds is a cross-group
                             comparison, undecidable earlier)
- KO advancement           → kickoff of the match the team WON to clinch the
                             predicted stage (winner: the final)
- eliminations (misses)    → kickoff of the match the team lost, or the
                             group anchor above if they never got out
- bonus questions          → BonusAnswer.resolved_at (the one true
                             "graded at" timestamp in the schema)

A pick whose fate is still open (team alive but short of the predicted
stage, group not complete, question unresolved) emits NO event — exactly
the cases where the engine currently pays nothing.
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models._datetime import aware_utc
from app.models.bonus import BonusAnswer, BonusPrediction
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score
from app.schemas.points_log import PointsLogChip, PointsLogEvent
from app.services import scoring
from app.services.bonus import answer_in, bonus_question_title, get_questions


# KO advancement path (excludes 'group' picks, which carry no point value,
# and 'third_place', which sits off the advancement path).
_STAGE_ORDER = ["round_of_32", "round_of_16", "quarter_final", "semi_final", "final", "winner"]
_STAGE_RANK = {s: i for i, s in enumerate(_STAGE_ORDER)}

# Winning a fixture at <key> clinches advancement to <value>.
_NEXT_STAGE = {
    "round_of_32": "round_of_16",
    "round_of_16": "quarter_final",
    "quarter_final": "semi_final",
    "semi_final": "final",
    "final": "winner",
}


async def build_points_log(
    session: AsyncSession, user_id: uuid.UUID
) -> list[PointsLogEvent]:
    """All point events for one user, newest first."""
    events: list[PointsLogEvent] = []
    events.extend(await _match_events(session, user_id))
    events.extend(await _advancement_events(session, user_id))
    events.extend(await _bonus_events(session, user_id))
    events.sort(key=lambda e: (e.ts, e.id), reverse=True)
    return events


# --- Match score events -------------------------------------------------------


async def _match_events(
    session: AsyncSession, user_id: uuid.UUID
) -> list[PointsLogEvent]:
    """One event per graded match prediction (mirrors the engine's match loop)."""
    config = scoring.get_scoring_config()
    match_cfg = config.get("match", {})
    outcome_pts = match_cfg.get("correct_outcome", 5)
    exact_pts = match_cfg.get("exact_score", 10)

    rows = (
        await session.execute(
            select(MatchPrediction, Score, Fixture)
            .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
            .outerjoin(Score, Fixture.id == Score.fixture_id)
            .where(
                MatchPrediction.user_id == user_id,
                Fixture.status == MatchStatus.FINISHED,
            )
        )
    ).all()
    if not rows:
        return []

    counts_by_fixture = await scoring.get_all_outcome_counts(session)

    events: list[PointsLogEvent] = []
    for prediction, score, fixture in rows:
        if not score:
            continue
        counts = counts_by_fixture.get(fixture.id, {"1": 0, "X": 0, "2": 0})
        total_predictors = sum(counts.values())
        # Graded on the REGULATION outcome, like the engine (see scoring.py).
        correct_predictors = counts.get(score.regulation_outcome, 0)
        points, is_outcome, is_exact = scoring.calculate_match_points(
            prediction,
            score,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
        )

        chips: list[PointsLogChip] = []
        if is_outcome:
            chips.append(PointsLogChip(label="Outcome", points=outcome_pts))
        if is_exact:
            chips.append(PointsLogChip(label="Exact score", points=exact_pts))
        rarity = points - (outcome_pts if is_outcome else 0) - (exact_pts if is_exact else 0)
        if rarity > 0:
            chips.append(PointsLogChip(label="Rarity bonus", points=rarity))

        events.append(
            PointsLogEvent(
                id=f"match:{fixture.id}",
                kind="match",
                ts=aware_utc(fixture.kickoff),
                points=points,
                is_miss=points == 0,
                phase=prediction.phase.value,
                stage=fixture.stage,
                group=fixture.group,
                fixture_id=fixture.id,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                predicted=f"{prediction.home_score}-{prediction.away_score}",
                # Regulation score, NOT final_home_score/final_away_score —
                # match predictions are always graded on the 90-minute result
                # (see Score.regulation_outcome), so the displayed score must
                # match what the pick was actually compared against, same as
                # the results page (matchBreakdown.ts reads score.home_score).
                actual=f"{score.home_score}-{score.away_score}",
                result="exact" if is_exact else "outcome" if is_outcome else "miss",
                chips=chips,
            )
        )
    return events


# --- Advancement events (R32 qualification + position bonus + KO bracket) -----


async def _advancement_events(
    session: AsyncSession, user_id: uuid.UUID
) -> list[PointsLogEvent]:
    """One event per (team, predicted stage) whose fate has resolved.

    Covers, in one uniform shape:
    - round_of_32: qualification base (+10) for the user's R32 bracket picks,
      with the group-position bonus (+5) folded in as a chip (or standing
      alone when the position was right but the team wasn't carried in the
      bracket);
    - round_of_16 … winner: KO advancement for Phase-1 and Phase-2 brackets,
      merged per team+stage, including the Phase-1→Phase-2 carry-forward.
    """
    # Imported inside the function to avoid pulling standings into the
    # scoring import chain (same pattern as scoring.py itself).
    from app.services.standings import (
        get_actual_group_standings,
        get_group_completion,
        get_predicted_group_standings,
        get_qualifying_third_place_teams,
    )

    config = scoring.get_scoring_config()
    adv_cfg = config.get("advancement", {})
    p2_cfg = adv_cfg.get("phase_2", {})
    pos_value = int(adv_cfg.get("group_position", 0))

    # -- Tournament-global state (same sources the engine reads) --
    completed_groups, all_groups = await get_group_completion(session)
    all_groups_complete = bool(all_groups) and completed_groups == all_groups
    actual_standings = await get_actual_group_standings(session)
    qualifying_third_names: set[str] = set()
    if all_groups_complete:
        thirds = await get_qualifying_third_place_teams(session)
        qualifying_third_names = {t["team"] for t in thirds}
    actual_advancement = await scoring.get_actual_advancement(session)

    # -- Timeline anchors --
    group_rows = (
        await session.execute(
            select(Fixture.group, Fixture.kickoff).where(Fixture.stage == "group")
        )
    ).all()
    group_last_kickoff: dict[str, datetime] = {}
    for g, kickoff in group_rows:
        if not g:
            continue
        kickoff = aware_utc(kickoff)
        if g not in group_last_kickoff or kickoff > group_last_kickoff[g]:
            group_last_kickoff[g] = kickoff
    thirds_ts: datetime | None = None
    if all_groups_complete and group_last_kickoff:
        thirds_ts = max(group_last_kickoff.values())

    team_group: dict[str, str] = {}
    team_actual_pos: dict[str, int] = {}
    for group, teams in actual_standings.items():
        if group not in completed_groups:
            continue
        for i, t in enumerate(teams):
            team_group[t["team"]] = group
            team_actual_pos[t["team"]] = i + 1

    def team_qualified(team: str) -> bool:
        pos = team_actual_pos.get(team)
        if pos in (1, 2):
            return True
        return pos == 3 and all_groups_complete and team in qualifying_third_names

    def qual_ts(team: str) -> datetime | None:
        """When this team's group fate resolved; None while still pending."""
        pos = team_actual_pos.get(team)
        if pos is None:
            return None  # group not complete
        if pos == 3:
            return thirds_ts  # best-8-thirds cut — None until all groups done
        return group_last_kickoff.get(team_group[team])

    # KO clinch + elimination times from finished knockout fixtures.
    ko_rows = (
        await session.execute(
            select(Fixture, Score)
            .outerjoin(Score, Fixture.id == Score.fixture_id)
            .where(Fixture.stage != "group", Fixture.status == MatchStatus.FINISHED)
            .order_by(Fixture.kickoff)
        )
    ).all()
    reach_ts: dict[tuple[str, str], datetime] = {}
    elim: dict[str, tuple[str, datetime]] = {}  # team -> (stage lost at, when)
    for fixture, score in ko_rows:
        if not score or fixture.stage not in _STAGE_RANK:
            continue  # skips third_place — off the advancement path
        ts = aware_utc(fixture.kickoff)
        # Appearing in a fixture at stage X is fallback evidence of reaching X
        # (kickoff-ordered, so setdefault keeps the earliest evidence).
        for t in (fixture.home_team, fixture.away_team):
            if t:
                reach_ts.setdefault((t, fixture.stage), ts)
        # `outcome` folds in ET/pens — KO matches always produce a winner.
        winner = loser = None
        if score.outcome == "1":
            winner, loser = fixture.home_team, fixture.away_team
        elif score.outcome == "2":
            winner, loser = fixture.away_team, fixture.home_team
        if winner:
            next_stage = _NEXT_STAGE.get(fixture.stage)
            if next_stage:
                reach_ts.setdefault((winner, next_stage), ts)
            if loser:
                elim[loser] = (fixture.stage, ts)

    # -- The user's stakes: bracket picks merged per (team, stage) --
    team_preds = (
        await session.execute(
            select(TeamPrediction).where(TeamPrediction.user_id == user_id)
        )
    ).scalars().all()
    has_phase2_bracket = any(p.phase == PredictionPhase.PHASE_2 for p in team_preds)

    stakes: dict[tuple[str, str], dict] = {}

    def add_stake(team: str, stage: str, phase_key: str, value: int, fallback: bool) -> None:
        st = stakes.setdefault(
            (team, stage), {"phase_1": None, "phase_2": None, "p2_fallback": False}
        )
        st[phase_key] = value
        if fallback:
            st["p2_fallback"] = True

    for pred in team_preds:
        if pred.stage not in _STAGE_RANK:
            continue  # 'group' picks carry no advancement value
        if pred.phase == PredictionPhase.PHASE_1:
            add_stake(pred.team, pred.stage, "phase_1", int(adv_cfg.get(pred.stage, 0)), False)
        else:
            add_stake(pred.team, pred.stage, "phase_2", int(p2_cfg.get(pred.stage, 0)), False)
    # Phase-1 → Phase-2 carry-forward: with no Phase-2 bracket at all, the
    # Phase-1 picks ALSO score under the Phase-2 table (mirrors the engine).
    # Zero-value stages (Phase-2 R32) are skipped so events don't get flagged
    # as carried when the carry contributes nothing.
    if not has_phase2_bracket:
        for pred in team_preds:
            if pred.phase != PredictionPhase.PHASE_1 or pred.stage not in _STAGE_RANK:
                continue
            carried = int(p2_cfg.get(pred.stage, 0))
            if carried > 0:
                add_stake(pred.team, pred.stage, "phase_2", carried, True)

    # The user's predicted group positions (for the +5 position bonus).
    predicted_pos: dict[str, int] = {}
    if pos_value > 0:
        predicted_standings, _ = await get_predicted_group_standings(session, user_id)
        for _group, teams in predicted_standings.items():
            for i, t in enumerate(teams):
                predicted_pos[t["team"]] = i + 1

    # -- Emit one event per resolved stake --
    events_by_key: dict[tuple[str, str], PointsLogEvent] = {}
    for (team, stage), st in stakes.items():
        potential = (st["phase_1"] or 0) + (st["phase_2"] or 0)
        if potential <= 0:
            continue  # e.g. a lone Phase-2 R32 pick — worth 0 by design

        actual_stage = actual_advancement.get(team)
        reached = (
            actual_stage is not None
            and _STAGE_RANK.get(actual_stage, -1) >= _STAGE_RANK[stage]
        )

        if reached:
            ts = qual_ts(team) if stage == "round_of_32" else reach_ts.get((team, stage))
            if ts is None:
                continue  # defensive: fate says reached but no anchor yet
            chips: list[PointsLogChip] = []
            if st["phase_1"]:
                chips.append(PointsLogChip(label="Phase I", points=st["phase_1"]))
            if st["phase_2"]:
                label = "Phase II · carried" if st["p2_fallback"] else "Phase II"
                chips.append(PointsLogChip(label=label, points=st["phase_2"]))
            points = sum(c.points for c in chips)
            phase = _phase_label(st)
            events_by_key[(team, stage)] = PointsLogEvent(
                id=f"adv:{stage}:{team}",
                kind="advance",
                ts=ts,
                points=points,
                is_miss=False,
                phase=phase,
                p2_fallback=st["p2_fallback"],
                stage=stage,
                group=team_group.get(team),
                team=team,
                predicted_position=predicted_pos.get(team),
                actual_position=team_actual_pos.get(team),
                third_place=team_actual_pos.get(team) == 3,
                chips=chips,
            )
        else:
            # Not reached: emit a miss only once the pick is definitively dead.
            elim_stage: str | None = None
            dead_ts: datetime | None = None
            if team in elim:
                elim_stage, dead_ts = elim[team]
            elif team in team_actual_pos and not team_qualified(team):
                elim_stage = "group"
                dead_ts = qual_ts(team)  # None while a 3rd-place fate is open
            if dead_ts is None:
                continue  # still alive (or fate pending) — engine pays nothing yet
            events_by_key[(team, stage)] = PointsLogEvent(
                id=f"adv:{stage}:{team}",
                kind="advance",
                ts=dead_ts,
                points=0,
                is_miss=True,
                phase=_phase_label(st),
                p2_fallback=st["p2_fallback"],
                stage=stage,
                group=team_group.get(team),
                team=team,
                predicted_position=predicted_pos.get(team),
                actual_position=team_actual_pos.get(team),
                third_place=team_actual_pos.get(team) == 3,
                elim_stage=elim_stage,
                chips=[],
            )

    # -- Group-position bonus (+5) — folds into the team's R32 event, or
    #    stands alone when the position was right without an R32 pick. --
    if pos_value > 0:
        for team, a_pos in team_actual_pos.items():
            if a_pos == 4 or predicted_pos.get(team) != a_pos:
                continue
            if not team_qualified(team):
                continue
            ts = qual_ts(team)
            if ts is None:
                continue  # 3rd-place fate pending
            chip = PointsLogChip(label="Exact position", points=pos_value)
            key = (team, "round_of_32")
            existing = events_by_key.get(key)
            if existing is not None:
                # A qualified team's R32 event is always an earned one (a miss
                # requires the team NOT to have reached R32), so folding in is safe.
                existing.chips.append(chip)
                existing.points += pos_value
                existing.is_miss = False
            else:
                events_by_key[key] = PointsLogEvent(
                    id=f"adv:round_of_32:{team}",
                    kind="advance",
                    ts=ts,
                    points=pos_value,
                    is_miss=False,
                    phase="phase_1",  # the bonus lives in the Phase-1 bucket
                    stage="round_of_32",
                    group=team_group.get(team),
                    team=team,
                    predicted_position=a_pos,
                    actual_position=a_pos,
                    third_place=a_pos == 3,
                    chips=[chip],
                )

    return list(events_by_key.values())


def _phase_label(st: dict) -> str:
    if st["phase_1"] and st["phase_2"]:
        return "both"
    if st["phase_2"]:
        return "phase_2"
    return "phase_1"


# --- Bonus-question events ----------------------------------------------------


async def _bonus_events(
    session: AsyncSession, user_id: uuid.UUID
) -> list[PointsLogEvent]:
    """One event per resolved bonus question the user answered.

    Correct picks mirror `services.bonus.get_bonus_results` exactly (same
    `answer_in` matching, same category points); wrong picks surface as
    0-point misses. Unresolved questions and blank answers emit nothing.
    """
    ans_rows = (await session.execute(select(BonusAnswer))).scalars().all()
    if not ans_rows:
        return []

    correct_by_qid: dict[str, list[str]] = {}
    resolved_by_qid: dict[str, datetime] = {}
    for a in ans_rows:
        correct_by_qid.setdefault(a.question_id, []).append(a.correct_answer)
        ts = aware_utc(a.resolved_at)
        if a.question_id not in resolved_by_qid or ts > resolved_by_qid[a.question_id]:
            resolved_by_qid[a.question_id] = ts

    pred_rows = (
        await session.execute(
            select(BonusPrediction)
            .where(BonusPrediction.user_id == user_id)
            .where(BonusPrediction.question_id.in_(list(correct_by_qid.keys())))
        )
    ).scalars().all()

    questions_by_id = {q.id: q for q in get_questions()}

    events: list[PointsLogEvent] = []
    for pred in pred_rows:
        question = questions_by_id.get(pred.question_id)
        corrects = correct_by_qid.get(pred.question_id, [])
        if question is None or not corrects:
            continue
        if not pred.answer:
            continue  # a saved-but-blank answer isn't a pick — no miss row
        is_correct = answer_in(pred.answer, corrects)
        points = question.points if is_correct else 0
        events.append(
            PointsLogEvent(
                id=f"bonus:{pred.question_id}",
                kind="bonus",
                ts=resolved_by_qid[pred.question_id],
                points=points,
                is_miss=not is_correct,
                question_label=bonus_question_title(question.label),
                answer=pred.answer,
                correct_answers=corrects,
                chips=(
                    [PointsLogChip(label="Bonus question", points=points)]
                    if is_correct
                    else []
                ),
            )
        )
    return events

"""Bracket-exposure computation.

Replaces the fixed `stubBracketExposure` on the frontend with a real
calculation of how many bracket points a user still has on the line.

Definition:
- "Points available" = sum of the scoring config's per-stage points for
  every knockout pick the user has locked in. Picks at stages that have
  already been played are credited only if the team actually advanced;
  picks at stages not yet played are assumed still alive (best case).
  Phase-aware: Phase 1 reads `advancement.<stage>` directly, Phase 2
  reads `advancement.phase_2.<stage>` — see `services/scoring.py` for
  the canonical lookup rule. There is no implicit multiplier.

- "Picks locked" / "picks total" — straightforward fraction of the
  bracket the user has filled in. Total is canonical to the FIFA 2026
  format (32 knockout picks across R32 → winner).

- "Final pick" — the (winner, opponent) pair extracted from the user's
  `winner` stage prediction and the other `final` stage prediction.

- "Alive per stage" — for each of R16 / QF / SF / Final / Winner, how
  many of the user's picks at that stage are teams that actually made it
  there (or beyond). Drives DwBracketAlive widget on the KO dashboard:
  numerator = alive count for the user, denominator = total teams at the
  stage (16/8/4/2/1). R32-stage scoring is excluded because R32-entry
  points are surfaced in DwGroupStageSummary's Qual column, not here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.score import Score
from app.services.scoring import get_scoring_config


# Map TeamPrediction.stage values → the scoring-config key for that stage.
# `group` is excluded — group-advance scoring is tracked differently and
# isn't part of "bracket exposure" in the dashboard's sense.
STAGE_POINT_KEY: dict[str, str] = {
    "round_of_32": "round_of_32",
    "round_of_16": "round_of_16",
    "quarter_final": "quarter_final",
    "semi_final": "semi_final",
    "final": "final",
    "winner": "winner",
}

# Canonical Phase 1 bracket pick counts for FIFA 2026 format:
#   16 R32 winners → 8 R16 winners → 4 QF → 2 SF → 1 final → 1 winner = 32 picks.
PICKS_PER_STAGE_PHASE_1: dict[str, int] = {
    "round_of_32": 16,
    "round_of_16": 8,
    "quarter_final": 4,
    "semi_final": 2,
    "final": 1,
    "winner": 1,
}
TOTAL_PHASE_1_BRACKET_PICKS = sum(PICKS_PER_STAGE_PHASE_1.values())

# Total teams competing at each KO stage. Used as the denominator in the
# DwBracketAlive widget — "4/16 picks alive at R16" reads as "4 of the 16
# teams playing R16 are teams the user predicted would be there."
TEAMS_AT_STAGE: dict[str, int] = {
    "round_of_16": 16,
    "quarter_final": 8,
    "semi_final": 4,
    "final": 2,
    "winner": 1,
}

# When the team WINS a match at stage X, they advance to stage Y.
# E.g. winning an R32 match means you made R16.
STAGE_ADVANCES_TO: dict[str, str] = {
    "round_of_32": "round_of_16",
    "round_of_16": "quarter_final",
    "quarter_final": "semi_final",
    "semi_final": "final",
    "final": "winner",
}

# Inverse: for a destination stage X, which prior stage's matches feed
# into X. Used to walk back from a user pick at X to the fixture whose
# outcome determines whether the pick is earned / available / eliminated.
STAGE_FED_BY: dict[str, str] = {dst: src for src, dst in STAGE_ADVANCES_TO.items()}


@dataclass
class StageCell:
    """A single earned/available bucket inside a stage row.

    n: count of the user's picks that fall into this bucket (after the
       per-tbd-match dedup for the `available` side).
    of: progressive denominator — for `earned` this is the number of feeder
       matches that have resolved at the prior stage; for `available` it's
       the number of feeder matches still tbd. The two together always add
       up to the prior stage's total fixture count.
    pts: n * (stage points from scoring config). Represents the points
       already credited (earned) or still possible (available).
    teams: the team codes that contributed to this bucket, oldest → newest
       feeder-match order. Used for tooltips.
    """

    n: int = 0
    of: int = 0
    pts: int = 0
    teams: list[str] = field(default_factory=list)


@dataclass
class StageRow:
    """One row of the Scoring Journey grid.

    Three buckets, which together account for every pick the user made at
    this stage:
      - earned    — feeder match finished, team won → reached (banked).
      - available — feeder match still TBD → still alive (in play).
      - missed    — feeder match finished, team lost → eliminated (0 pts).
    The grouped-bars widget renders these as the green / gold / muted-red
    segments of a single bar; (earned + available + missed) is the
    denominator for the "picks kept" fraction. `missed` carries no points
    (pts=0) — it exists so the eliminated teams can be surfaced rather than
    silently dropped."""

    earned: StageCell = field(default_factory=StageCell)
    available: StageCell = field(default_factory=StageCell)
    missed: StageCell = field(default_factory=StageCell)


@dataclass
class BracketExposureResult:
    """Plain dataclass for the service result; API layer wraps in Pydantic."""

    points_available: int
    picks_locked: int
    picks_total: int
    final_winner: str | None
    final_opponent: str | None
    # alive_per_stage[stage] = number of user picks at that stage that are
    # teams that actually made it to (or past) that stage in the tournament.
    # Keys: round_of_16, quarter_final, semi_final, final, winner.
    # Kept for backwards compat with the v1 DwBracketAlive widget. The
    # per_stage breakdown below subsumes its purpose.
    alive_per_stage: dict[str, int] = field(default_factory=dict)
    # teams_per_stage[stage] = total teams at that stage (the denominator
    # for the dashboard table). Constant for FIFA 2026; returned for
    # convenience so the frontend doesn't have to hardcode.
    teams_per_stage: dict[str, int] = field(default_factory=lambda: dict(TEAMS_AT_STAGE))
    # per_stage[stage] = {earned: {…}, available: {…}}. Drives the v4
    # Scoring Journey widget. Stages: round_of_16, quarter_final,
    # semi_final, final, winner.
    per_stage: dict[str, StageRow] = field(default_factory=dict)


async def _compute_teams_that_made_stage(session: AsyncSession) -> dict[str, set[str]]:
    """For each KO stage, return the set of teams that have actually made
    it to that stage based on finished match results.

    A team "made" R16 if they won an R32 match. They "made" QF if they won
    an R16 match. And so on. Computed from existing Score.outcome data — no
    new ingest required.

    Returns a dict keyed by stage_advanced_to (the destination stage), e.g.
    `{"round_of_16": {"USA", "ARG", ...}, "quarter_final": {...}, ...}`.
    """
    result = await session.execute(
        select(Fixture, Score)
        .join(Score, Score.fixture_id == Fixture.id)
        .where(Fixture.status == MatchStatus.FINISHED)
        .where(Fixture.stage.in_(list(STAGE_ADVANCES_TO.keys())))
    )
    teams_at_stage: dict[str, set[str]] = {dest: set() for dest in STAGE_ADVANCES_TO.values()}
    for fixture, score in result.all():
        # Score.outcome: "1" home win, "X" draw, "2" away win.
        # KO matches resolve via extra-time / penalties — the scorer
        # resolves draws by promoting the eventual winner's side.
        if score.outcome == "1":
            winner_team = fixture.home_team
        elif score.outcome == "2":
            winner_team = fixture.away_team
        else:
            continue  # defensive: draw in a KO match shouldn't happen
        destination = STAGE_ADVANCES_TO.get(fixture.stage)
        if destination:
            teams_at_stage[destination].add(winner_team)
    return teams_at_stage


async def _classify_picks_per_stage(
    session: AsyncSession,
    user_picks_by_stage: dict[str, list[str]],
    stage_points_lookup: dict[str, int],
) -> dict[str, StageRow]:
    """For every destination stage that has a feeder round, walk through the
    feeder fixtures and classify the user's picks into earned/available
    buckets.

    `user_picks_by_stage[stage]` is the list of teams the user predicted
    to make `stage` (i.e. predicted to win their feeder match). Order is
    preserved so the resulting `teams` lists mirror prediction order.

    Per destination stage X:
      1. Look at every fixture at the feeder stage X-1.
      2. Each FINISHED match contributes its winner to `earned_teams`
         and bumps `known_count`.
      3. Each unfinished match is recorded in `tbd_matches` and bumps
         `tbd_count`.
      4. Iterate the user's picks at X:
           - team reached X (won its feeder match) → earned bucket
           - else the team is still ALIVE (qualified to the R32 and not knocked
             out) → available bucket; picks sharing the SAME pending feeder
             match are deduped (only one of the two can advance)
           - else (team is OUT — lost a KO match or never qualified) → missed

    A pick at a DEEP round whose feeder fixtures are still `slot:` placeholders
    (the bracket hasn't been drawn there yet) stays AVAILABLE while its team is
    alive — it is NOT mislabelled "missed" just because no feeder fixture names
    it yet. Only genuinely-eliminated teams land in `missed`.

    `pts` is `n × stage_points`. `teams` lists every pick that landed in
    that bucket — for `available` we include all picks even when their
    tbd match already counted once (so the tooltip can show both names).
    """
    out: dict[str, StageRow] = {}

    # Pre-fetch every KO fixture once. Outer-join Score so unfinished
    # fixtures (no Score row yet) still come back.
    result = await session.execute(
        select(Fixture, Score)
        .join(Score, Score.fixture_id == Fixture.id, isouter=True)
        .where(Fixture.stage.in_(list(STAGE_ADVANCES_TO.keys())))
    )
    rows = list(result.all())

    # Teams still alive in the tournament: those that qualified to the KO
    # (appear in an R32 fixture) and have NOT been knocked out (didn't lose a
    # finished KO match — `score.outcome` resolves ET/pens). A pick whose team
    # is alive but hasn't reached the stage yet is IN PLAY, even when its feeder
    # fixture is still a slot placeholder; only genuinely-out teams are missed.
    qualified: set[str] = set()
    eliminated: set[str] = set()
    for fixture, score in rows:
        if fixture.stage == "round_of_32":
            qualified.add(fixture.home_team)
            qualified.add(fixture.away_team)
        if fixture.status == MatchStatus.FINISHED and score is not None:
            if score.outcome == "1":
                eliminated.add(fixture.away_team)
            elif score.outcome == "2":
                eliminated.add(fixture.home_team)
    alive_teams = qualified - eliminated

    for dest_stage in TEAMS_AT_STAGE:
        feeder_stage = STAGE_FED_BY.get(dest_stage)
        if not feeder_stage:
            out[dest_stage] = StageRow()
            continue

        earned_teams: set[str] = set()
        tbd_matches: list[tuple[str, str]] = []
        known_count = 0
        tbd_count = 0

        for fixture, score in rows:
            if fixture.stage != feeder_stage:
                continue
            if fixture.status == MatchStatus.FINISHED and score is not None:
                known_count += 1
                if score.outcome == "1":
                    earned_teams.add(fixture.home_team)
                elif score.outcome == "2":
                    earned_teams.add(fixture.away_team)
                # "X" in a KO match is a missing-resolution edge case; the
                # scorer is expected to promote a winner via ET/pens. We
                # count the match as resolved but credit no team.
            else:
                tbd_count += 1
                tbd_matches.append((fixture.home_team, fixture.away_team))

        picks_at_stage = user_picks_by_stage.get(dest_stage, [])
        earned_picks: list[str] = []
        available_picks: list[str] = []
        eliminated_picks: list[str] = []
        counted_tbd_matches: set[tuple[str, str]] = set()
        loose_available = 0  # alive picks not tied to a known pending feeder match

        for team in picks_at_stage:
            if team in earned_teams:
                earned_picks.append(team)
                continue
            if team in alive_teams:
                # Still in the tournament → in play, even if its feeder fixture
                # isn't drawn yet. Dedup picks that share the same pending match
                # (only one of the two can advance); count the rest individually.
                available_picks.append(team)
                match = next(((h, a) for h, a in tbd_matches if team in (h, a)), None)
                if match is not None:
                    counted_tbd_matches.add(match)
                else:
                    loose_available += 1
            else:
                # Out of the tournament: lost a KO match or never qualified.
                eliminated_picks.append(team)

        available_n = len(counted_tbd_matches) + loose_available
        stage_pts = stage_points_lookup.get(STAGE_POINT_KEY[dest_stage], 0)
        out[dest_stage] = StageRow(
            earned=StageCell(
                n=len(earned_picks),
                of=known_count,
                pts=len(earned_picks) * stage_pts,
                teams=earned_picks,
            ),
            available=StageCell(
                n=available_n,
                of=tbd_count,
                pts=available_n * stage_pts,
                teams=available_picks,
            ),
            missed=StageCell(
                n=len(eliminated_picks),
                of=known_count,
                pts=0,
                teams=eliminated_picks,
            ),
        )

    return out


async def compute_bracket_exposure(
    session: AsyncSession,
    user_id: uuid.UUID,
    phase: PredictionPhase = PredictionPhase.PHASE_1,
) -> BracketExposureResult:
    """Compute the user's bracket exposure for the given phase."""
    result = await session.execute(
        select(TeamPrediction)
        .where(TeamPrediction.user_id == user_id)
        .where(TeamPrediction.phase == phase)
    )
    preds = list(result.scalars().all())

    # Knockout-stage picks only — ignore 'group' stage predictions which
    # belong to group_advance scoring, not bracket exposure.
    ko_preds = [p for p in preds if p.stage in STAGE_POINT_KEY]

    config = get_scoring_config()
    adv = config.get("advancement", {})
    # Per-phase stage point tables — Phase 2 nests under advancement.phase_2.
    stage_points = adv.get("phase_2", {}) if phase == PredictionPhase.PHASE_2 else adv

    points_available = 0
    for p in ko_preds:
        key = STAGE_POINT_KEY[p.stage]
        points_available += stage_points.get(key, 0)

    # Final pair: pull the user's winner pick and the other 'final' pick.
    winner_team = next((p.team for p in ko_preds if p.stage == "winner"), None)
    final_teams = [p.team for p in ko_preds if p.stage == "final"]
    final_opponent = None
    if winner_team:
        # The opponent is whichever finalist isn't the winner. If the user
        # only picked one finalist (the winner) we leave opponent as None.
        for t in final_teams:
            if t != winner_team:
                final_opponent = t
                break

    # Alive-per-stage: kept for the v1 DwBracketAlive contract. Computed
    # from the same finished-match data the new per-stage breakdown reads.
    teams_that_made_stage = await _compute_teams_that_made_stage(session)
    alive_per_stage: dict[str, int] = {}
    for stage_key in TEAMS_AT_STAGE:
        user_picks_at_stage = {p.team for p in ko_preds if p.stage == stage_key}
        actual_at_stage = teams_that_made_stage.get(stage_key, set())
        alive_per_stage[stage_key] = len(user_picks_at_stage & actual_at_stage)

    # v4 per-stage breakdown — drives DwScoringJourney.
    user_picks_by_stage: dict[str, list[str]] = {}
    for p in ko_preds:
        user_picks_by_stage.setdefault(p.stage, []).append(p.team)
    per_stage = await _classify_picks_per_stage(
        session, user_picks_by_stage, stage_points
    )

    return BracketExposureResult(
        points_available=points_available,
        picks_locked=len(ko_preds),
        picks_total=TOTAL_PHASE_1_BRACKET_PICKS,
        final_winner=winner_team,
        final_opponent=final_opponent,
        alive_per_stage=alive_per_stage,
        teams_per_stage=dict(TEAMS_AT_STAGE),
        per_stage=per_stage,
    )

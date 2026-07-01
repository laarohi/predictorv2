"""Bonus-question service.

Loads question definitions from `config/worldcup2026.yml`, scores user
predictions against the admin-entered correct answers, and exposes
helpers for the API layer.

Question definitions live in the YAML, not the DB. The DB only holds
per-user picks (BonusPrediction) and per-competition correct answers
(BonusAnswer). Adding/removing a question is a config change, not a
migration.
"""

from __future__ import annotations

import unicodedata
import uuid
from dataclasses import dataclass
from typing import Iterable, Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.config import get_tournament_config
from app.models.bonus import BonusAnswer, BonusPrediction
from app.models.fifa_ranking import FifaRanking
from app.models.fixture import Fixture, MatchStatus
from app.services.fifa_codes import FIFA_CODE_TO_TEAM_NAME


BonusCategory = Literal["group_stage", "top_flop", "awards"]
BonusInputType = Literal["team", "player"]


@dataclass
class BonusQuestion:
    """One question as rendered for the wizard / admin UI."""

    id: str
    category: BonusCategory
    label: str  # cutoff.rank already substituted into "{n}" token
    input_type: BonusInputType
    points: int
    # For team-input questions with a YAML `cutoff:` block, the pre-filtered
    # list of competition teams that satisfy the cutoff (e.g. "in top 7" or
    # "outside top 12"). The frontend uses this to filter the team dropdown.
    # None = no restriction (no cutoff configured, or non-team question).
    eligible_teams: list[str] | None = None


# ---- Config loading ---------------------------------------------------------


def _get_bonus_config() -> dict:
    """Return the `bonus:` section of the tournament config, or empty dict."""
    try:
        config = get_tournament_config()
    except FileNotFoundError:
        return {}
    return config.get("bonus", {}) or {}


def _category_points(bonus_cfg: dict, category: BonusCategory) -> int:
    """Look up the configured point value for a category, defaulting to 0."""
    return int(bonus_cfg.get("points", {}).get(category, 0))


async def get_fifa_rankings(session: AsyncSession) -> list[str]:
    """Return our tournament-team subset of the live FIFA ranking, ordered
    by rank (index 0 = rank #1). Returns an empty list if the table is
    empty — consumers must handle that case (the standings tiebreaker
    falls through to alphabetical; bonus-question cutoffs return empty
    eligibility lists).

    The `fifa_rankings` table holds all 211 ranked teams; this filters to
    teams that appear in our `FIFA_CODE_TO_TEAM_NAME` mapping so consumers
    (tiebreakers, bonus eligibility) see the canonical DB team names they
    already expect. Populate the table via
    `scripts/sync_fifa_rankings.py`."""
    rows = (
        await session.execute(
            select(FifaRanking).order_by(FifaRanking.rank)
        )
    ).scalars().all()
    return [
        FIFA_CODE_TO_TEAM_NAME[r.country_code]
        for r in rows
        if r.country_code in FIFA_CODE_TO_TEAM_NAME
    ]


async def fetch_competition_teams(session: AsyncSession) -> set[str]:
    """All distinct *resolved* team names from the fixtures table. Excludes
    the legacy 'TBD' marker and the 'slot:<stage>:<id>:<side>' placeholders
    that fixture_sync.py writes for unresolved knockout matches — those
    aren't real teams and would leak into bonus-question dropdowns
    (specifically `dark_horse`, whose 'outside top N' cutoff doesn't
    naturally filter them out the way `flop`'s 'inside top N' intersection
    does).

    The DB is populated by the Football-Data API import
    (services/fixture_sync.py), so it reflects the real qualifiers."""
    rows = (
        await session.execute(
            select(Fixture.home_team, Fixture.away_team).distinct()
        )
    ).all()
    teams: set[str] = set()
    for home, away in rows:
        for name in (home, away):
            if name and name != "TBD" and not name.startswith("slot:"):
                teams.add(name)
    return teams


def _eligible_teams_for_cutoff(
    cutoff: dict,
    rankings: list[str],
    competition_teams: set[str],
) -> list[str]:
    """Apply a question's cutoff to the rankings + competition team set.

    cutoff.direction = 'inside'  → eligible = competition ∩ rankings[:rank]
                       'outside' → eligible = competition − rankings[:rank]
                                   (i.e. teams ranked below `rank`, plus any
                                   competition team not on the ranking list)
    Returns a sorted list for deterministic API responses."""
    n = int(cutoff.get("rank", 0))
    direction = str(cutoff.get("direction", "inside"))
    top_n_set = set(rankings[:n])
    if direction == "inside":
        return sorted(t for t in competition_teams if t in top_n_set)
    # 'outside' is the default for any non-'inside' value — defensive against
    # typos like 'out' or 'above'.
    return sorted(t for t in competition_teams if t not in top_n_set)


def get_question_top_n_set(
    question_id: str,
    rankings: list[str] | None = None,
) -> set[str]:
    """Return the FIFA top-N set for a question's cutoff. The rank comes from
    the question's `cutoff:` block in YAML; the team list comes from
    `rankings` (defaults to the YAML snapshot). Empty set if either is missing.

    This is the *raw* top-N set — it includes all teams in the rankings up to
    N regardless of whether they're in the competition. Callers that need the
    competition-intersected set (e.g. `compute_bottlers`) intersect after.

    Pass `rankings=` from a caller that has resolved them from the DB
    (`get_fifa_rankings()`); omit when ranking-based filtering isn't
    needed (e.g. validation-only call sites that just want
    `question.points`)."""
    if rankings is None:
        rankings = []
    cfg = _get_bonus_config()
    for q in cfg.get("questions", []) or []:
        if q.get("id") == question_id:
            n = int((q.get("cutoff") or {}).get("rank", 0))
            return set(rankings[:n])
    return set()


def get_questions(
    competition_teams: set[str] | None = None,
    rankings: list[str] | None = None,
) -> list[BonusQuestion]:
    """Load the list of bonus questions from YAML, with per-question label
    token substitution and (if `competition_teams` is provided) pre-computed
    eligible_teams for team-input questions that have a `cutoff:` block.

    Pass `competition_teams=None` from contexts that don't need dropdown
    filtering — e.g. question-id validation, points lookup. In those cases
    every question's `eligible_teams` stays `None` and the question metadata
    is returned without a DB-derived team intersection.

    Pass `competition_teams=<set>` (typically from `fetch_competition_teams`)
    from contexts that *do* need the filtered list — e.g. the public bonus
    questions API route, the admin listing route.

    Pass `rankings=` from a caller that has resolved them from the DB
    (`get_fifa_rankings()`); omit when ranking-based filtering isn't
    needed (e.g. validation-only call sites)."""
    cfg = _get_bonus_config()
    if rankings is None:
        rankings = []
    raw_qs = cfg.get("questions", []) or []
    questions: list[BonusQuestion] = []
    for raw in raw_qs:
        category: BonusCategory = raw.get("category", "group_stage")
        cutoff = raw.get("cutoff") or None
        # Substitute {n} with the question's cutoff rank (no-op if no cutoff).
        label = raw.get("label") or ""
        if cutoff:
            label = label.replace("{n}", str(cutoff.get("rank", "")))
        input_type = raw.get("input_type", "team")
        eligible_teams: list[str] | None = None
        if cutoff and input_type == "team" and competition_teams is not None:
            eligible_teams = _eligible_teams_for_cutoff(
                cutoff, rankings, competition_teams
            )
        questions.append(
            BonusQuestion(
                id=raw["id"],
                category=category,
                label=label,
                input_type=input_type,
                points=_category_points(cfg, category),
                eligible_teams=eligible_teams,
            )
        )
    return questions


# ---- Player-name normalization ---------------------------------------------


def _normalize(s: str) -> str:
    """Case-fold + strip accents so 'Mbappé' matches 'mbappe'. Used for both
    team and player answer comparison; team names usually exact-match anyway,
    but this is forgiving."""
    if not s:
        return ""
    decomposed = unicodedata.normalize("NFKD", s)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.casefold().strip()


def answers_match(user_answer: str, correct_answer: str) -> bool:
    """Compare two free-text answers leniently (case- and accent-insensitive)."""
    return _normalize(user_answer) == _normalize(correct_answer)


def answer_in(user_answer: str, correct_answers: list[str]) -> bool:
    """True if `user_answer` matches any one of `correct_answers`. Used
    for bonus questions where multiple teams may tie on the criterion
    (e.g. two teams scoring the same number of goals in the group stage)
    — picking any of the tied teams should award full points."""
    if not user_answer:
        return False
    n = _normalize(user_answer)
    return any(_normalize(c) == n for c in correct_answers)


# ---- Scoring ----------------------------------------------------------------


@dataclass
class BonusResult:
    """One bonus question a user answered correctly, with points earned —
    the per-question detail behind calculate_bonus_points()'s total."""

    question_id: str
    label: str
    points: int


async def get_bonus_results(
    session: AsyncSession,
    user_id: uuid.UUID,
    competition_id: uuid.UUID | None = None,
) -> list[BonusResult]:
    """Bonus questions a user answered CORRECTLY, with points earned each.

    For each question with a recorded correct answer (in `bonus_answers`),
    check whether the user's prediction matches via answer_in() and record
    the question's category points if so. calculate_bonus_points() is just
    sum(r.points for r in this) — kept separate so the leaderboard's
    per-question breakdown panel and the plain point total share one
    correctness check instead of two.
    """
    # Load all bonus answers (optionally filtered by competition). Each
    # question may have several rows now — one per tied correct answer.
    ans_q = select(BonusAnswer)
    if competition_id is not None:
        ans_q = ans_q.where(BonusAnswer.competition_id == competition_id)
    ans_rows = (await session.execute(ans_q)).scalars().all()
    if not ans_rows:
        return []

    correct_by_qid: dict[str, list[str]] = {}
    for a in ans_rows:
        correct_by_qid.setdefault(a.question_id, []).append(a.correct_answer)

    # User's predictions for those questions.
    pred_rows = (
        await session.execute(
            select(BonusPrediction)
            .where(BonusPrediction.user_id == user_id)
            .where(BonusPrediction.question_id.in_(list(correct_by_qid.keys())))
        )
    ).scalars().all()

    # Map question ID → question definition (label + category points).
    questions_by_id: dict[str, BonusQuestion] = {q.id: q for q in get_questions()}

    results: list[BonusResult] = []
    for pred in pred_rows:
        corrects = correct_by_qid.get(pred.question_id)
        question = questions_by_id.get(pred.question_id)
        if not corrects or question is None:
            continue
        # Full points if the user picked any of the tied correct answers.
        if answer_in(pred.answer, corrects):
            results.append(
                BonusResult(question_id=question.id, label=question.label, points=question.points)
            )
    return results


async def calculate_bonus_points(
    session: AsyncSession,
    user_id: uuid.UUID,
    competition_id: uuid.UUID | None = None,
) -> int:
    """Total bonus points earned by a user — sum of get_bonus_results()."""
    results = await get_bonus_results(session, user_id, competition_id)
    return sum(r.points for r in results)


# ---- Auto-computed answers --------------------------------------------------
#
# The four group-stage questions (Goal Machine, Toothless Attack, The Sieve,
# The Fortress) and the two top/flop questions (Dark Horse, Bottlers) can be
# derived directly from fixtures + scores. The Awards section cannot — those
# come from the FIFA awards ceremony and must be entered manually.
#
# The compute functions below are pure (operate on plain data, no DB I/O)
# so they're trivially unit-testable. `compute_bonus_answers_for_competition`
# is the thin async orchestrator that loads from the DB and calls them.


# Stage rank for "how far did this team progress". Group stage = 0, winner
# = 6. Used by the dark-horse and bottlers calculators.
_STAGE_ORDER = ["group", "round_of_32", "round_of_16", "quarter_final", "semi_final", "final"]
_STAGE_RANK = {s: i for i, s in enumerate(_STAGE_ORDER)}
# Winner is one step above "final" — represents winning the final (not just
# reaching it). Used in dark-horse comparisons so a winning underdog out-
# ranks a finalist who lost the final.
_WINNER_RANK = len(_STAGE_ORDER)


def compute_group_stats(fixtures_with_scores: Iterable[Fixture]) -> dict[str, dict[str, int]]:
    """Aggregate {team: {gf, ga}} from finished group-stage fixtures only.

    Pure function — pass it any iterable of Fixture objects with their
    .score relationship preloaded. Fixtures without a final score, with
    placeholder team names ("TBD"), or in non-group stages are skipped.
    """
    stats: dict[str, dict[str, int]] = {}
    for f in fixtures_with_scores:
        if f.stage != "group":
            continue
        if f.status != MatchStatus.FINISHED:
            continue
        score = getattr(f, "score", None)
        if score is None:
            continue
        if not f.home_team or f.home_team == "TBD":
            continue
        if not f.away_team or f.away_team == "TBD":
            continue
        h = stats.setdefault(f.home_team, {"gf": 0, "ga": 0})
        a = stats.setdefault(f.away_team, {"gf": 0, "ga": 0})
        h["gf"] += score.home_score
        h["ga"] += score.away_score
        a["gf"] += score.away_score
        a["ga"] += score.home_score
    return stats


def compute_team_progress(fixtures_with_scores: Iterable[Fixture]) -> dict[str, str]:
    """For each team, the furthest stage they have *definitively* reached
    according to completed fixtures. A team that only appears in group
    fixtures (no knockout appearance yet) ends up at "group". The winner
    of a finished final gets the special "winner" stage."""
    progress: dict[str, str] = {}
    final_winner: str | None = None
    for f in fixtures_with_scores:
        if f.status != MatchStatus.FINISHED:
            continue
        if f.stage not in _STAGE_RANK:
            continue
        if not f.home_team or f.home_team == "TBD":
            continue
        if not f.away_team or f.away_team == "TBD":
            continue
        rank = _STAGE_RANK[f.stage]
        for team in (f.home_team, f.away_team):
            existing = _STAGE_RANK.get(progress.get(team, "group"), 0)
            if rank > existing or team not in progress:
                progress[team] = f.stage
        # Determine the final winner — used to bump them past plain "final".
        if f.stage == "final":
            score = getattr(f, "score", None)
            if score is not None:
                outcome = score.outcome
                if outcome == "1":
                    final_winner = f.home_team
                elif outcome == "2":
                    final_winner = f.away_team
    if final_winner:
        progress[final_winner] = "winner"
    return progress


def _teams_with_extremum(
    stats: dict[str, dict[str, int]], key: str, want_max: bool
) -> list[str]:
    """Return the team(s) whose stats[key] is the max (or min). Empty if
    no stats. Ties are returned in alphabetical order so the list is
    deterministic — admins reading the auto-suggestion see a stable set."""
    if not stats:
        return []
    values = [s[key] for s in stats.values()]
    target = max(values) if want_max else min(values)
    return sorted(t for t, s in stats.items() if s[key] == target)


def compute_dark_horse(progress: dict[str, str], fifa_top: set[str]) -> list[str]:
    """Team(s) NOT in `fifa_top` with the furthest progression. Empty if
    no non-top team has played any completed match yet."""
    if not progress:
        return []
    candidates: dict[str, int] = {}
    for team, stage in progress.items():
        if team in fifa_top:
            continue
        rank = _WINNER_RANK if stage == "winner" else _STAGE_RANK.get(stage, 0)
        candidates[team] = rank
    if not candidates:
        return []
    max_rank = max(candidates.values())
    return sorted(t for t, r in candidates.items() if r == max_rank)


def compute_bottlers(
    progress: dict[str, str], fifa_top: set[str], competition_teams: set[str]
) -> list[str]:
    """Top-N team(s) with the earliest exit (lowest stage rank). Only
    considers top-N teams that are actually in the competition. A top
    team with no finished fixtures yet is treated as still at "group"."""
    top_in_comp = [t for t in fifa_top if t in competition_teams]
    if not top_in_comp:
        return []
    ranks = {t: _STAGE_RANK.get(progress.get(t, "group"), 0) for t in top_in_comp}
    # Skip the winner — they didn't "bottle" anything.
    ranks = {t: r for t, r in ranks.items() if progress.get(t) != "winner"}
    if not ranks:
        return []
    min_rank = min(ranks.values())
    return sorted(t for t, r in ranks.items() if r == min_rank)


async def compute_bonus_answers_for_competition(
    session: AsyncSession,
    competition_id: uuid.UUID,
) -> dict[str, list[str]]:
    """Compute auto-derived correct answers for every question that
    *can* be auto-derived. Awards-category questions get an empty list
    (they're manual-only). The returned dict maps question_id → list of
    correct answers (multiple = a tie). Callers can decide whether to
    surface as a suggestion (current admin flow) or persist directly."""
    fx_rows = (
        await session.execute(
            select(Fixture)
            .where(Fixture.competition_id == competition_id)
            .options(selectinload(Fixture.score))
        )
    ).scalars().all()

    stats = compute_group_stats(fx_rows)
    progress = compute_team_progress(fx_rows)
    competition_teams: set[str] = set()
    for f in fx_rows:
        for t in (f.home_team, f.away_team):
            if t and t != "TBD":
                competition_teams.add(t)

    # Per-question top-N sets — pulled from each question's `cutoff:` block
    # so dark_horse and flop can use different cutoffs (e.g. 12 vs 7).
    # Resolve rankings once so both questions see a consistent FIFA top-N
    # list. Empty when the table hasn't been synced yet (no auto-suggested
    # answers in that case, which is the right fail-safe).
    rankings = await get_fifa_rankings(session)
    dark_horse_top = get_question_top_n_set("dark_horse", rankings=rankings)
    flop_top = get_question_top_n_set("flop", rankings=rankings)

    return {
        "most_goals_scored_group": _teams_with_extremum(stats, "gf", True),
        "least_goals_scored_group": _teams_with_extremum(stats, "gf", False),
        "most_goals_conceded_group": _teams_with_extremum(stats, "ga", True),
        "least_goals_conceded_group": _teams_with_extremum(stats, "ga", False),
        "dark_horse": compute_dark_horse(progress, dark_horse_top),
        "flop": compute_bottlers(progress, flop_top, competition_teams),
        # Awards questions intentionally omitted — manual only.
    }

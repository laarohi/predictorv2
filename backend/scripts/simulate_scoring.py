"""Monte Carlo scoring calibration simulator.

Generates synthetic tournaments + synthetic predictors, runs them through
the real `LogarithmicScoring` and `calculate_advancement_points` code,
and reports how points decompose by source.

Use it to answer questions like:
- Does the group stage overpower the knockouts?
- Does the tournament winner typically have picked the correct champion?
- How much does Phase 2 actually contribute?
- How dominant is the exact-score bonus?

Predictor model
---------------
Each team has a *true strength* drawn from FIFA rankings (top 25 from
config) and a synthetic tier for the remaining 23 teams. Each match's
goal expectations follow a Poisson model around team strength.

Each predictor has a *skill* parameter (precision). Their personal team
strength perception is the true strength plus Gaussian noise scaled by
1/skill. They predict matches and brackets using their noisy perception
through the same Poisson model, so high-skill predictors are more often
right without being deterministic.

CLI
---
    docker compose exec backend python scripts/simulate_scoring.py \
        --tournaments 500 --predictors 30 --seed 42

Sensitivity sweeps for the four calibration knobs are run automatically
and saved to docs/scoring-calibration-report.md.
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# Make `app.*` importable when run via `python scripts/simulate_scoring.py`
# from inside the backend container or from the host.
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.models.prediction import PredictionPhase  # noqa: E402
from app.services import scoring as scoring_module  # noqa: E402
from app.services.scoring import (  # noqa: E402
    LogarithmicScoring,
    calculate_advancement_points,
)


# ---------------------------------------------------------------------------
# Duck-typed objects matching the scoring API's expected attributes.
# The real scoring code accepts anything with the right properties, so we
# avoid pulling SQLModel/DB dependencies into the simulator.
# ---------------------------------------------------------------------------


@dataclass
class FakeScore:
    """Stand-in for app.models.Score that LogarithmicScoring can consume."""

    home_score: int
    away_score: int

    @property
    def outcome(self) -> str:
        if self.home_score > self.away_score:
            return "1"
        if self.home_score < self.away_score:
            return "2"
        return "X"

    @property
    def final_home_score(self) -> int:
        return self.home_score

    @property
    def final_away_score(self) -> int:
        return self.away_score


@dataclass
class FakeMatchPrediction:
    """Stand-in for app.models.MatchPrediction."""

    home_score: int
    away_score: int

    @property
    def predicted_outcome(self) -> str:
        if self.home_score > self.away_score:
            return "1"
        if self.home_score < self.away_score:
            return "2"
        return "X"


# ---------------------------------------------------------------------------
# Tournament model
# ---------------------------------------------------------------------------


@dataclass
class Team:
    name: str
    fifa_rank: int  # 1 = strongest
    strength: float  # log-odds scale, higher = stronger


@dataclass
class GroupMatch:
    group: str
    home: Team
    away: Team
    home_goals: int
    away_goals: int


@dataclass
class KnockoutMatch:
    stage: str  # singular: round_of_32, round_of_16, quarter_final, semi_final, final
    home: Team
    away: Team
    home_goals: int
    away_goals: int
    winner: Team  # forced — knockout matches have no draws


@dataclass
class TournamentReality:
    teams: list[Team]
    groups: dict[str, list[Team]]
    group_matches: list[GroupMatch]
    # Team -> highest stage reached, matching get_actual_advancement()'s shape:
    #   {"France": "winner", "Germany": "semi_final", "Norway": "round_of_32", ...}
    advancement: dict[str, str]
    knockout_matches: list[KnockoutMatch]
    champion: Team
    # Bonus answers
    bonus_truth: dict[str, str]
    # Final group standings, ordered (index 0 = 1st place). Used for the
    # Phase 1 group_position bonus scoring path.
    group_standings: dict[str, list[Team]] = field(default_factory=dict)
    # Names of the 8 third-placed teams that qualified for R32.
    qualifying_thirds: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Team setup
# ---------------------------------------------------------------------------

# Strength is on the log-odds scale used by the Poisson goal model:
#   lambda = GOAL_BASE * exp(GOAL_COEF * (s_self - s_opp))
# Calibrated so a top side averages ~1.9 goals against a minnow and
# a balanced match averages ~1.3 goals per side.
GOAL_BASE = 1.30
GOAL_COEF = 0.40


def build_teams(rng: random.Random) -> list[Team]:
    """Build 48 teams. The FIFA top 25 are a hardcoded baseline (this is a
    simulator — we don't need the live FIFA ranking here, just a plausible
    distribution of team strengths). The remaining 23 are synthetic
    mid/lower-tier teams."""
    # Stable snapshot from April 2026 — order is what matters for the
    # tier/strength curve, not name freshness. If you want to re-baseline,
    # paste the first 25 from `SELECT team_name FROM fifa_rankings ORDER BY rank LIMIT 25`.
    fifa_ranking = [
        "France", "Spain", "Argentina", "England", "Portugal",
        "Brazil", "Netherlands", "Morocco", "Belgium", "Germany",
        "Croatia", "Italy", "Colombia", "Senegal", "Mexico",
        "United States", "Uruguay", "Japan", "Switzerland", "Denmark",
        "Iran", "Turkey", "Ecuador", "Austria", "South Korea",
    ]

    teams: list[Team] = []
    # Tier 1 (1-12): strength roughly +1.5 down to +0.6
    # Tier 2 (13-25): +0.6 down to +0.1
    # Tier 3 (26-36): +0.1 down to -0.3 (synthetic)
    # Tier 4 (37-48): -0.3 down to -0.7 (synthetic)
    #
    # We just lerp between rank 1 (strength 1.5) and rank 48 (strength -0.7)
    # so the strength surface is smooth.
    def strength_for_rank(rank: int) -> float:
        top, bottom = 1.5, -0.7
        return top - (rank - 1) * (top - bottom) / 47

    # Take FIFA top 25 as-is (some may not be in the WC field — for the
    # simulator that's fine, they're just teams).
    for i, name in enumerate(fifa_ranking[:25]):
        rank = i + 1
        teams.append(Team(name=name, fifa_rank=rank, strength=strength_for_rank(rank)))

    # 23 synthetic teams to fill the 48-team field.
    for i in range(25, 48):
        rank = i + 1
        teams.append(
            Team(
                name=f"Team{rank:02d}",
                fifa_rank=rank,
                strength=strength_for_rank(rank),
            )
        )

    return teams


def assign_groups(teams: list[Team], rng: random.Random) -> dict[str, list[Team]]:
    """Pot draw: 4 pots of 12 teams ordered by strength. Each group gets
    one team from each pot."""
    pots = [teams[i * 12 : (i + 1) * 12] for i in range(4)]
    groups: dict[str, list[Team]] = {chr(ord("A") + i): [] for i in range(12)}
    for pot in pots:
        shuffled = pot.copy()
        rng.shuffle(shuffled)
        for i, team in enumerate(shuffled):
            groups[chr(ord("A") + i)].append(team)
    return groups


# ---------------------------------------------------------------------------
# Match simulation (Poisson goal model)
# ---------------------------------------------------------------------------


def poisson(lam: float, rng: random.Random) -> int:
    """Knuth's Poisson sampler. Good enough for lam < 30."""
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k - 1


def simulate_goals(
    home: Team, away: Team, rng: random.Random, cap: int = 8
) -> tuple[int, int]:
    """Sample regular-time goals for both teams via independent Poisson."""
    lam_h = GOAL_BASE * math.exp(GOAL_COEF * (home.strength - away.strength))
    lam_a = GOAL_BASE * math.exp(GOAL_COEF * (away.strength - home.strength))
    return min(poisson(lam_h, rng), cap), min(poisson(lam_a, rng), cap)


def simulate_knockout_match(
    home: Team, away: Team, stage: str, rng: random.Random
) -> KnockoutMatch:
    """Generate a knockout match; if drawn in regular time, the stronger
    side wins on penalties with their strength as a soft bias."""
    h, a = simulate_goals(home, away, rng)
    if h == a:
        # ET/penalties: stronger team wins with prob softmax(strength gap).
        bias = 1.0 / (1.0 + math.exp(-1.5 * (home.strength - away.strength)))
        winner = home if rng.random() < bias else away
    else:
        winner = home if h > a else away
    return KnockoutMatch(stage=stage, home=home, away=away, home_goals=h, away_goals=a, winner=winner)


# ---------------------------------------------------------------------------
# Group stage + qualification
# ---------------------------------------------------------------------------


def simulate_group_stage(
    groups: dict[str, list[Team]], rng: random.Random
) -> tuple[list[GroupMatch], dict[str, list[tuple[Team, dict]]]]:
    """Round-robin within each group. Returns matches + ordered standings.

    Standings entry per team: (Team, {points, gf, ga, gd, played})
    """
    matches: list[GroupMatch] = []
    standings: dict[str, list[tuple[Team, dict]]] = {}

    for group_name, group_teams in groups.items():
        table: dict[str, dict] = {t.name: {"team": t, "pts": 0, "gf": 0, "ga": 0} for t in group_teams}
        for i in range(len(group_teams)):
            for j in range(i + 1, len(group_teams)):
                home, away = group_teams[i], group_teams[j]
                h, a = simulate_goals(home, away, rng)
                matches.append(GroupMatch(group=group_name, home=home, away=away, home_goals=h, away_goals=a))
                table[home.name]["gf"] += h
                table[home.name]["ga"] += a
                table[away.name]["gf"] += a
                table[away.name]["ga"] += h
                if h > a:
                    table[home.name]["pts"] += 3
                elif h < a:
                    table[away.name]["pts"] += 3
                else:
                    table[home.name]["pts"] += 1
                    table[away.name]["pts"] += 1

        # Sort by points, GD, GF, then a tiny random tiebreak so identical
        # rows don't always favor the alphabetically-first team.
        ranked = sorted(
            table.values(),
            key=lambda r: (
                r["pts"],
                r["gf"] - r["ga"],
                r["gf"],
                rng.random(),
            ),
            reverse=True,
        )
        standings[group_name] = [(r["team"], r) for r in ranked]

    return matches, standings


def qualify_for_knockout(
    standings: dict[str, list[tuple[Team, dict]]],
    rng: random.Random,
) -> tuple[list[Team], list[Team], list[Team]]:
    """Top 2 per group + best 8 of the 12 third-placed teams.

    Returns (firsts, seconds, thirds_qualified)."""
    firsts: list[Team] = []
    seconds: list[Team] = []
    thirds_candidates: list[tuple[Team, dict]] = []

    for group_name, ranked in standings.items():
        firsts.append(ranked[0][0])
        seconds.append(ranked[1][0])
        thirds_candidates.append(ranked[2])

    thirds_candidates.sort(
        key=lambda r: (r[1]["pts"], r[1]["gf"] - r[1]["ga"], r[1]["gf"], rng.random()),
        reverse=True,
    )
    thirds = [t for t, _ in thirds_candidates[:8]]
    return firsts, seconds, thirds


# ---------------------------------------------------------------------------
# Knockout bracket
# ---------------------------------------------------------------------------


def simulate_knockout(
    qualified: list[Team], rng: random.Random
) -> tuple[list[KnockoutMatch], dict[str, str], Team]:
    """32 teams → R32 → R16 → QF → SF → F.

    Returns (all knockout matches, team→highest stage, champion).
    The advancement dict matches the schema get_actual_advancement() uses
    in the real backend, including the "winner" entry for the champion."""
    matches: list[KnockoutMatch] = []
    advancement: dict[str, str] = {t.name: "round_of_32" for t in qualified}

    bracket = qualified.copy()
    rng.shuffle(bracket)

    stage_order = [
        ("round_of_32", "round_of_16"),
        ("round_of_16", "quarter_final"),
        ("quarter_final", "semi_final"),
        ("semi_final", "final"),
        ("final", "winner"),
    ]

    for stage, next_stage in stage_order:
        next_round: list[Team] = []
        for i in range(0, len(bracket), 2):
            home, away = bracket[i], bracket[i + 1]
            m = simulate_knockout_match(home, away, stage, rng)
            matches.append(m)
            # Both teams reached this stage.
            for t in (home, away):
                advancement[t.name] = stage
            # Winner advances to next.
            advancement[m.winner.name] = next_stage
            next_round.append(m.winner)
        bracket = next_round

    champion = bracket[0]
    return matches, advancement, champion


# ---------------------------------------------------------------------------
# Bonus question truth
# ---------------------------------------------------------------------------


def compute_bonus_truth(
    teams: list[Team],
    group_matches: list[GroupMatch],
    advancement: dict[str, str],
) -> dict[str, str]:
    """Resolve the YAML bonus questions against the simulated reality.

    Awards/player questions can't be modeled without players, so we fold
    them into 'team-shaped' proxies (likely-best-team-of-tournament etc.)
    to still have a denominator for accuracy."""
    # Group-stage goal totals.
    gf = Counter()
    ga = Counter()
    for m in group_matches:
        gf[m.home.name] += m.home_goals
        gf[m.away.name] += m.away_goals
        ga[m.home.name] += m.away_goals
        ga[m.away.name] += m.home_goals

    most_gf = max(gf.items(), key=lambda x: x[1])[0]
    least_gf = min(gf.items(), key=lambda x: x[1])[0]
    most_ga = max(ga.items(), key=lambda x: x[1])[0]
    least_ga = min(ga.items(), key=lambda x: x[1])[0]

    # Top/flop: dark horse = best progression outside FIFA top 12.
    # Flop = team inside FIFA top 7 that bowed out earliest.
    stage_rank = {
        "group": 0,
        "round_of_32": 1,
        "round_of_16": 2,
        "quarter_final": 3,
        "semi_final": 4,
        "final": 5,
        "winner": 6,
    }

    by_rank = {t.name: t.fifa_rank for t in teams}
    dark_horses = [t for t in teams if t.fifa_rank > 12]
    dark_horse = max(
        dark_horses,
        key=lambda t: stage_rank.get(advancement.get(t.name, "group"), 0),
    ).name
    inside_top7 = [t for t in teams if t.fifa_rank <= 7]
    flop = min(
        inside_top7,
        key=lambda t: stage_rank.get(advancement.get(t.name, "group"), 0),
    ).name

    # Awards proxies: pick the strongest team that reached the latest stage
    # as a stand-in for the player awards. We just need a stable ground
    # truth a predictor can match against.
    award_proxy = max(
        teams,
        key=lambda t: (stage_rank.get(advancement.get(t.name, "group"), 0), -t.fifa_rank),
    ).name

    return {
        "most_goals_scored_group": most_gf,
        "least_goals_scored_group": least_gf,
        "most_goals_conceded_group": most_ga,
        "least_goals_conceded_group": least_ga,
        "dark_horse": dark_horse,
        "flop": flop,
        "best_player": award_proxy,
        "top_scorer": award_proxy,
        "best_young_player": award_proxy,
        "golden_glove": award_proxy,
    }


def simulate_reality(rng: random.Random) -> TournamentReality:
    teams = build_teams(rng)
    groups = assign_groups(teams, rng)
    group_matches, standings = simulate_group_stage(groups, rng)
    firsts, seconds, thirds = qualify_for_knockout(standings, rng)
    qualified = firsts + seconds + thirds
    knockout_matches, advancement, champion = simulate_knockout(qualified, rng)
    bonus_truth = compute_bonus_truth(teams, group_matches, advancement)
    # Flatten standings -> {group: [Team in 1st..4th order]} for the
    # group_position bonus path.
    group_standings = {g: [t for t, _ in rows] for g, rows in standings.items()}
    qualifying_thirds = {t.name for t in thirds}
    return TournamentReality(
        teams=teams,
        groups=groups,
        group_matches=group_matches,
        knockout_matches=knockout_matches,
        advancement=advancement,
        champion=champion,
        bonus_truth=bonus_truth,
        group_standings=group_standings,
        qualifying_thirds=qualifying_thirds,
    )


# ---------------------------------------------------------------------------
# Predictor model
# ---------------------------------------------------------------------------


@dataclass
class Predictor:
    name: str
    skill: float  # higher = lower noise

    def perceive(self, teams: list[Team], rng: random.Random) -> dict[str, float]:
        """Predictor's noisy view of true team strengths. The noise std
        is 1/skill on the log-odds scale, so a skill=2 predictor's
        perception is twice as tight as skill=1."""
        sigma = 1.0 / max(self.skill, 0.1)
        return {t.name: t.strength + rng.gauss(0, sigma) for t in teams}


@dataclass
class PredictorScore:
    """Decomposed points by source. Numbers are designed to add up to
    `total` so the report can show ratios cleanly."""

    name: str
    skill: float

    # Group-stage related
    group_match_outcome: int = 0
    group_match_exact: int = 0
    group_match_rarity: int = 0

    # Knockout-stage match prediction (Phase 2)
    knockout_match_outcome: int = 0
    knockout_match_exact: int = 0
    knockout_match_rarity: int = 0

    # Bracket advancement (Phase 1 + Phase 2 combined buckets per stage)
    r32: int = 0
    r16: int = 0
    qf: int = 0
    sf: int = 0
    final: int = 0
    winner: int = 0

    # Phase 1 group_position bonus (predicted standings derived from
    # group match score predictions; paid for correctly-placed qualifiers).
    group_position: int = 0

    # Bonus
    bonus: int = 0

    # Tracking
    correct_champion: bool = False

    @property
    def group_total(self) -> int:
        return (
            self.group_match_outcome
            + self.group_match_exact
            + self.group_match_rarity
            + self.group_position
        )

    @property
    def knockout_match_total(self) -> int:
        return self.knockout_match_outcome + self.knockout_match_exact + self.knockout_match_rarity

    @property
    def bracket_total(self) -> int:
        return self.r32 + self.r16 + self.qf + self.sf + self.final + self.winner

    @property
    def exact_total(self) -> int:
        return self.group_match_exact + self.knockout_match_exact

    @property
    def rarity_total(self) -> int:
        return self.group_match_rarity + self.knockout_match_rarity

    @property
    def total(self) -> int:
        return (
            self.group_total
            + self.knockout_match_total
            + self.bracket_total
            + self.bonus
        )


# ---------------------------------------------------------------------------
# Predictor's bracket projection (their "mental tournament")
# ---------------------------------------------------------------------------


def project_mental_bracket(
    perception: dict[str, float],
    reality: TournamentReality,
    rng: random.Random,
) -> dict[str, str]:
    """Run a single stochastic tournament from the predictor's POV.

    Returns {team_name: highest_stage}. The "stage" values are singular
    to match what real scoring expects."""

    def mental_match(h: Team, a: Team) -> Team:
        lam_h = GOAL_BASE * math.exp(GOAL_COEF * (perception[h.name] - perception[a.name]))
        lam_a = GOAL_BASE * math.exp(GOAL_COEF * (perception[a.name] - perception[h.name]))
        gh, ga = poisson(lam_h, rng), poisson(lam_a, rng)
        if gh == ga:
            bias = 1.0 / (1.0 + math.exp(-1.5 * (perception[h.name] - perception[a.name])))
            return h if rng.random() < bias else a
        return h if gh > ga else a

    # Simulate groups using predictor's perceptions.
    advancement: dict[str, str] = {t.name: "group" for t in reality.teams}
    standings: dict[str, list[tuple[Team, dict]]] = {}
    for group_name, group_teams in reality.groups.items():
        table = {t.name: {"team": t, "pts": 0, "gf": 0, "ga": 0} for t in group_teams}
        for i in range(len(group_teams)):
            for j in range(i + 1, len(group_teams)):
                h, a = group_teams[i], group_teams[j]
                lam_h = GOAL_BASE * math.exp(GOAL_COEF * (perception[h.name] - perception[a.name]))
                lam_a = GOAL_BASE * math.exp(GOAL_COEF * (perception[a.name] - perception[h.name]))
                gh, ga = poisson(lam_h, rng), poisson(lam_a, rng)
                table[h.name]["gf"] += gh
                table[h.name]["ga"] += ga
                table[a.name]["gf"] += ga
                table[a.name]["ga"] += gh
                if gh > ga:
                    table[h.name]["pts"] += 3
                elif gh < ga:
                    table[a.name]["pts"] += 3
                else:
                    table[h.name]["pts"] += 1
                    table[a.name]["pts"] += 1
        ranked = sorted(
            table.values(),
            key=lambda r: (r["pts"], r["gf"] - r["ga"], r["gf"], rng.random()),
            reverse=True,
        )
        standings[group_name] = [(r["team"], r) for r in ranked]

    firsts = [s[0][0] for s in standings.values()]
    seconds = [s[1][0] for s in standings.values()]
    thirds_candidates = [s[2] for s in standings.values()]
    thirds_candidates.sort(
        key=lambda r: (r[1]["pts"], r[1]["gf"] - r[1]["ga"], r[1]["gf"], rng.random()),
        reverse=True,
    )
    thirds = [t for t, _ in thirds_candidates[:8]]
    qualified = firsts + seconds + thirds
    for t in qualified:
        advancement[t.name] = "round_of_32"

    bracket = qualified.copy()
    rng.shuffle(bracket)
    for stage, next_stage in [
        ("round_of_32", "round_of_16"),
        ("round_of_16", "quarter_final"),
        ("quarter_final", "semi_final"),
        ("semi_final", "final"),
        ("final", "winner"),
    ]:
        next_round: list[Team] = []
        for i in range(0, len(bracket), 2):
            h, a = bracket[i], bracket[i + 1]
            for t in (h, a):
                advancement[t.name] = stage
            w = mental_match(h, a)
            advancement[w.name] = next_stage
            next_round.append(w)
        bracket = next_round

    return advancement


def predict_score(
    h: Team,
    a: Team,
    perception: dict[str, float],
    rng: random.Random,
) -> tuple[int, int]:
    """Predicted home/away goals from the predictor's perspective."""
    lam_h = GOAL_BASE * math.exp(GOAL_COEF * (perception[h.name] - perception[a.name]))
    lam_a = GOAL_BASE * math.exp(GOAL_COEF * (perception[a.name] - perception[h.name]))
    return poisson(lam_h, rng), poisson(lam_a, rng)


def predict_bonus(
    perception: dict[str, float],
    bonus_truth: dict[str, str],
    teams: list[Team],
    rng: random.Random,
    skill: float,
) -> dict[str, str]:
    """For each bonus question, predictor either picks the true answer
    (probability proportional to skill) or a random plausible team."""
    # Probability they get it right scales with skill, capped low because
    # bonus questions are hard. At skill 1.5 → ~25% correct, skill 0.5 → ~8%.
    p_right = min(0.6, 0.15 * skill)
    out: dict[str, str] = {}
    team_names = [t.name for t in teams]
    for q_id, truth in bonus_truth.items():
        if rng.random() < p_right:
            out[q_id] = truth
        else:
            out[q_id] = rng.choice(team_names)
    return out


# ---------------------------------------------------------------------------
# One simulation pass
# ---------------------------------------------------------------------------


@dataclass
class SimRun:
    config: dict[str, Any]
    label: str
    tournaments: list[list[PredictorScore]] = field(default_factory=list)
    champions: list[str] = field(default_factory=list)
    winner_skills: list[float] = field(default_factory=list)
    winner_picked_champion: list[bool] = field(default_factory=list)


def simulate_one(
    predictors: list[Predictor],
    rng: random.Random,
    config: dict[str, Any],
) -> tuple[list[PredictorScore], Team]:
    """Run one tournament. Returns scores per predictor + the champion."""
    reality = simulate_reality(rng)

    # Patch the scoring config readers so calculate_advancement_points and
    # LogarithmicScoring see the sweep's config instead of the YAML.
    original = scoring_module.get_scoring_config
    scoring_module.get_scoring_config = lambda: config
    try:
        return _score(predictors, reality, rng, config), reality.champion
    finally:
        scoring_module.get_scoring_config = original


def _score(
    predictors: list[Predictor],
    reality: TournamentReality,
    rng: random.Random,
    config: dict[str, Any],
) -> list[PredictorScore]:
    match_cfg = config["match"]
    base_outcome = match_cfg["correct_outcome"]
    base_exact = match_cfg["exact_score"]

    strategy = LogarithmicScoring()

    # Each predictor generates one full set of predictions.
    perceptions = [p.perceive(reality.teams, rng) for p in predictors]
    mental_brackets = [
        project_mental_bracket(perceptions[i], reality, rng) for i in range(len(predictors))
    ]

    # Match predictions (group + knockout).
    group_preds_by_match: list[list[FakeMatchPrediction]] = []
    for m in reality.group_matches:
        preds = []
        for perc in perceptions:
            h, a = predict_score(m.home, m.away, perc, rng)
            preds.append(FakeMatchPrediction(home_score=h, away_score=a))
        group_preds_by_match.append(preds)

    knockout_preds_by_match: list[list[FakeMatchPrediction]] = []
    for m in reality.knockout_matches:
        preds = []
        for perc in perceptions:
            h, a = predict_score(m.home, m.away, perc, rng)
            preds.append(FakeMatchPrediction(home_score=h, away_score=a))
        knockout_preds_by_match.append(preds)

    bonus_preds = [
        predict_bonus(perceptions[i], reality.bonus_truth, reality.teams, rng, predictors[i].skill)
        for i in range(len(predictors))
    ]

    scores = [PredictorScore(name=p.name, skill=p.skill) for p in predictors]

    # Score group matches.
    for m, preds in zip(reality.group_matches, group_preds_by_match):
        score = FakeScore(home_score=m.home_goals, away_score=m.away_goals)
        # Rarity needs the room's outcome distribution.
        outcome_counts: Counter[str] = Counter(p.predicted_outcome for p in preds)
        total_predictors = sum(outcome_counts.values())
        correct_predictors = outcome_counts.get(score.outcome, 0)
        for i, pred in enumerate(preds):
            pts, correct, exact = strategy.calculate(
                pred, score, match_cfg, total_predictors, correct_predictors
            )
            # Decompose: base + exact + rarity.
            if correct:
                scores[i].group_match_outcome += base_outcome
                rarity = pts - base_outcome - (base_exact if exact else 0)
                if rarity > 0:
                    scores[i].group_match_rarity += rarity
            if exact:
                scores[i].group_match_exact += base_exact

    # Score knockout matches (Phase 2 — but match predictions don't take
    # a phase multiplier; only advancement does).
    for m, preds in zip(reality.knockout_matches, knockout_preds_by_match):
        score = FakeScore(home_score=m.home_goals, away_score=m.away_goals)
        outcome_counts = Counter(p.predicted_outcome for p in preds)
        total_predictors = sum(outcome_counts.values())
        correct_predictors = outcome_counts.get(score.outcome, 0)
        for i, pred in enumerate(preds):
            pts, correct, exact = strategy.calculate(
                pred, score, match_cfg, total_predictors, correct_predictors
            )
            if correct:
                scores[i].knockout_match_outcome += base_outcome
                rarity = pts - base_outcome - (base_exact if exact else 0)
                if rarity > 0:
                    scores[i].knockout_match_rarity += rarity
            if exact:
                scores[i].knockout_match_exact += base_exact

    # Score brackets. Each predictor's "mental bracket" generates one team
    # prediction per team at the team's highest stage. We score the same
    # bracket once under Phase 1 (full reward) and once under Phase 2
    # (independent table — Phase 2 R32=0, R16=5, etc.). The real app does
    # the same: a user's Phase 1 picks lock at the pre-tournament deadline
    # and the Phase 2 picks they re-submit after groups score independently.
    for i, mental in enumerate(mental_brackets):
        for team_name, predicted_stage in mental.items():
            if predicted_stage == "group":
                continue
            pred = MagicMock()
            pred.team = team_name
            pred.stage = predicted_stage
            for phase in (PredictionPhase.PHASE_1, PredictionPhase.PHASE_2):
                pred.phase = phase
                pts = calculate_advancement_points(
                    pred,
                    reality.advancement,
                    phase,
                )
                if pts > 0:
                    if predicted_stage == "round_of_32":
                        scores[i].r32 += pts
                    elif predicted_stage == "round_of_16":
                        scores[i].r16 += pts
                    elif predicted_stage == "quarter_final":
                        scores[i].qf += pts
                    elif predicted_stage == "semi_final":
                        scores[i].sf += pts
                    elif predicted_stage == "final":
                        scores[i].final += pts
                    elif predicted_stage == "winner":
                        scores[i].winner += pts

    # Phase 1 group_position bonus. Mirrors the backend path:
    # derive each predictor's standings from their group score predictions,
    # then award `advancement.group_position` per team where predicted
    # position == actual position AND team qualified.
    adv_cfg = config.get("advancement", {})
    position_bonus_value = adv_cfg.get("group_position", 0)
    if position_bonus_value > 0:
        # actual_positions[group][team_name] -> 1..4
        actual_positions: dict[str, dict[str, int]] = {
            g: {t.name: i + 1 for i, t in enumerate(ranked)}
            for g, ranked in reality.group_standings.items()
        }

        # Map each match index to its group for fast lookup.
        match_group = [m.group for m in reality.group_matches]

        for i in range(len(predictors)):
            # Build predicted standings tables from this predictor's
            # group match predictions.
            tables: dict[str, dict[str, dict]] = {
                g: {t.name: {"team": t, "pts": 0, "gf": 0, "ga": 0} for t in reality.groups[g]}
                for g in reality.groups
            }
            for j, m in enumerate(reality.group_matches):
                pred = group_preds_by_match[j][i]
                t = tables[match_group[j]]
                h, a = pred.home_score, pred.away_score
                t[m.home.name]["gf"] += h
                t[m.home.name]["ga"] += a
                t[m.away.name]["gf"] += a
                t[m.away.name]["ga"] += h
                if h > a:
                    t[m.home.name]["pts"] += 3
                elif h < a:
                    t[m.away.name]["pts"] += 3
                else:
                    t[m.home.name]["pts"] += 1
                    t[m.away.name]["pts"] += 1

            for group, table in tables.items():
                ranked = sorted(
                    table.values(),
                    key=lambda r: (r["pts"], r["gf"] - r["ga"], r["gf"], rng.random()),
                    reverse=True,
                )
                actual_by_team = actual_positions.get(group, {})
                for idx, row in enumerate(ranked):
                    predicted_position = idx + 1
                    name = row["team"].name
                    if actual_by_team.get(name) != predicted_position:
                        continue
                    if predicted_position == 4:
                        continue
                    if predicted_position in (1, 2) or (
                        predicted_position == 3 and name in reality.qualifying_thirds
                    ):
                        scores[i].group_position += position_bonus_value

    # Bonus.
    bonus_points = config.get("bonus_points", {"group_stage": 15, "top_flop": 20, "awards": 20})
    bonus_category = {
        "most_goals_scored_group": "group_stage",
        "least_goals_scored_group": "group_stage",
        "most_goals_conceded_group": "group_stage",
        "least_goals_conceded_group": "group_stage",
        "dark_horse": "top_flop",
        "flop": "top_flop",
        "best_player": "awards",
        "top_scorer": "awards",
        "best_young_player": "awards",
        "golden_glove": "awards",
    }
    for i, pred_map in enumerate(bonus_preds):
        for q_id, ans in pred_map.items():
            if ans == reality.bonus_truth[q_id]:
                scores[i].bonus += bonus_points[bonus_category[q_id]]

    # Track if winner picked the actual champion.
    for i, s in enumerate(scores):
        # The mental bracket's "winner" pick is whichever team it placed
        # at stage="winner".
        mental = mental_brackets[i]
        their_champion = next(
            (name for name, stage in mental.items() if stage == "winner"), None
        )
        s.correct_champion = their_champion == reality.champion.name

    return scores


# ---------------------------------------------------------------------------
# Configuration variants
# ---------------------------------------------------------------------------


def baseline_config() -> dict[str, Any]:
    """Mirror the current YAML config — Phase 1 + Phase 2 advancement
    tables are independent, no phase_multipliers."""
    return {
        "mode": "logarithmic",
        "match": {
            "correct_outcome": 5,
            "exact_score": 10,
            "rarity_cap": 10,
            "hybrid_cap": 10,
        },
        "advancement": {
            # Phase 1 — full reward, pre-tournament uncertainty.
            "round_of_32": 10,
            "round_of_16": 15,
            "quarter_final": 25,
            "semi_final": 55,
            "final": 85,
            "winner": 150,
            "group_position": 5,
            # Phase 2 — explicit per-stage; bracket is partly determined by
            # group results so R32/R16 are deliberately squashed.
            "phase_2": {
                "round_of_32": 0,
                "round_of_16": 5,
                "quarter_final": 15,
                "semi_final": 40,
                "final": 60,
                "winner": 100,
            },
        },
        "bonus_points": {
            "group_stage": 15,
            "top_flop": 20,
            "awards": 20,
        },
    }


def variant(name: str, mutator) -> tuple[str, dict[str, Any]]:
    cfg = baseline_config()
    mutator(cfg)
    return name, cfg


def all_variants() -> list[tuple[str, dict[str, Any]]]:
    """The sensitivity sweep menu.

    Baseline is now the *target* calibration (recommended Phase 1 +
    explicit Phase 2 + group_position bonus). Other variants explore
    nearby points in the calibration space."""

    def tame_rarity(c):
        c["match"]["rarity_cap"] = 5

    def tame_exact(c):
        c["match"]["exact_score"] = 7

    def boost_phase2(c):
        """Push Phase 2 closer to Phase 1 (less of a discount)."""
        c["advancement"]["phase_2"] = {
            "round_of_32": 5,
            "round_of_16": 10,
            "quarter_final": 20,
            "semi_final": 45,
            "final": 70,
            "winner": 120,
        }

    def tame_phase2(c):
        """Push Phase 2 further down (bigger discount)."""
        c["advancement"]["phase_2"] = {
            "round_of_32": 0,
            "round_of_16": 0,
            "quarter_final": 10,
            "semi_final": 30,
            "final": 45,
            "winner": 80,
        }

    def boost_winner(c):
        """How far does champ-pick rate climb if we just keep raising W?"""
        c["advancement"]["winner"] = 200
        c["advancement"]["phase_2"]["winner"] = 140

    def tame_group_position(c):
        """What if the group_position bonus were 3 instead of 5?"""
        c["advancement"]["group_position"] = 3

    def no_group_position(c):
        """Calibration sanity check: how much does the group_position
        bonus actually contribute to champ-pick rate / group share?"""
        c["advancement"]["group_position"] = 0

    return [
        ("baseline (current YAML)", baseline_config()),
        variant("tame_rarity_bonus (cap 5)", tame_rarity),
        variant("tame_exact_score (exact 7)", tame_exact),
        variant("boost_phase2 (closer to Phase 1)", boost_phase2),
        variant("tame_phase2 (R16=0, deeper discount)", tame_phase2),
        variant("boost_winner (P1 W 200 / P2 W 140)", boost_winner),
        variant("tame_group_position (3 pts)", tame_group_position),
        variant("no_group_position (0 pts)", no_group_position),
    ]


# ---------------------------------------------------------------------------
# Predictor pool
# ---------------------------------------------------------------------------


def build_predictors(n: int, rng: random.Random) -> list[Predictor]:
    """Build n predictors with skill drawn from a realistic mix."""
    predictors: list[Predictor] = []
    # 10% experts, 70% average, 20% weak.
    for i in range(n):
        r = rng.random()
        if r < 0.10:
            skill = rng.uniform(1.4, 1.8)  # very tight perception
        elif r < 0.80:
            skill = rng.uniform(0.8, 1.3)  # average-ish
        else:
            skill = rng.uniform(0.4, 0.7)  # noisy
        predictors.append(Predictor(name=f"P{i:02d}", skill=skill))
    return predictors


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def aggregate_run(run: SimRun) -> dict[str, Any]:
    """Compute aggregate metrics from a SimRun."""
    winner_totals: list[int] = []
    winner_skills: list[float] = []
    winner_picked_champion: list[bool] = []

    # Per-source averages computed across the winning predictor of each tournament.
    winner_components = {
        k: []
        for k in [
            "group_match_outcome",
            "group_match_exact",
            "group_match_rarity",
            "group_position",
            "knockout_match_outcome",
            "knockout_match_exact",
            "knockout_match_rarity",
            "r32",
            "r16",
            "qf",
            "sf",
            "final",
            "winner",
            "bonus",
        ]
    }

    # Skill-vs-rank correlation: spearman-ish on average rank by skill.
    skill_rank_pairs: list[tuple[float, int]] = []

    for tourney_scores in run.tournaments:
        ranked = sorted(tourney_scores, key=lambda s: s.total, reverse=True)
        winner = ranked[0]
        winner_totals.append(winner.total)
        winner_skills.append(winner.skill)
        winner_picked_champion.append(winner.correct_champion)
        for k in winner_components:
            winner_components[k].append(getattr(winner, k))

        for rank, s in enumerate(ranked, start=1):
            skill_rank_pairs.append((s.skill, rank))

    def mean(xs):
        return statistics.mean(xs) if xs else 0.0

    def pct(xs):
        return 100.0 * sum(xs) / len(xs) if xs else 0.0

    # Spearman-ish: just correlation of (skill, rank).
    skills, ranks = zip(*skill_rank_pairs)
    skill_mean = statistics.mean(skills)
    rank_mean = statistics.mean(ranks)
    num = sum((s - skill_mean) * (r - rank_mean) for s, r in zip(skills, ranks))
    den_s = math.sqrt(sum((s - skill_mean) ** 2 for s in skills))
    den_r = math.sqrt(sum((r - rank_mean) ** 2 for r in ranks))
    corr_skill_rank = num / (den_s * den_r) if (den_s * den_r) else 0.0

    return {
        "n_tournaments": len(run.tournaments),
        "avg_winner_total": mean(winner_totals),
        "avg_winner_skill": mean(winner_skills),
        "pct_winner_picked_champion": pct(winner_picked_champion),
        "corr_skill_vs_rank": corr_skill_rank,  # negative = higher skill → lower rank# (good)
        "winner_components": {k: mean(v) for k, v in winner_components.items()},
    }


def render_report(results: list[tuple[str, dict[str, Any]]], n_tournaments: int, n_predictors: int) -> str:
    lines: list[str] = []
    lines.append("# Scoring Calibration Report")
    lines.append("")
    lines.append(
        f"Monte Carlo simulation across **{n_tournaments} tournaments** with "
        f"**{n_predictors} predictors** per tournament. The simulator uses the "
        f"real `LogarithmicScoring` and `calculate_advancement_points` code so "
        f"the numbers reflect what the actual app would award.\n"
    )
    lines.append("**Methodology** — Each team has a strength on a log-odds scale "
        "(FIFA top-25 ranking + synthetic mid/lower tiers). Match outcomes are "
        "Poisson(strength-difference) goals. Each predictor has a personal "
        "*skill* (perception precision); they predict matches using their noisy "
        "perception through the same Poisson model. Higher skill = better "
        "predictions, but never deterministic. Predictors also run a 'mental "
        "tournament' to produce their bracket. Phase 1 + Phase 2 advancement "
        "predictions are both scored (Phase 2 at the multiplier in config).\n"
    )
    lines.append("## Reading the table")
    lines.append("")
    lines.append("Each row is one config variant. Columns:\n")
    lines.append("- **Winner pts** — average total points of the tournament-winning predictor")
    lines.append("- **% picked champ** — fraction of tournaments where the winning predictor's bracket "
        "had the actual champion at `stage=winner`. **Higher is better** "
        "(the user wants winners to typically have nailed the champion).")
    lines.append("- **Skill→rank corr** — correlation between predictor skill and final rank. "
        "Negative is better — means higher-skill predictors finish higher. "
        "A corr close to 0 means luck is dominating skill.")
    lines.append("- **Group %** / **Knockout %** / **Bracket %** / **Bonus %** — for the average "
        "winner, what fraction of their total came from each source")
    lines.append("- **Exact %** — fraction of winner's total that came from the +10 exact-score bonus")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Big comparison table.
    headers = [
        "Variant",
        "Winner pts",
        "% picked champ",
        "Skill→rank corr",
        "Group %",
        "Knockout match %",
        "Bracket %",
        "Bonus %",
        "Exact %",
        "Rarity %",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for label, agg in results:
        wc = agg["winner_components"]
        total = agg["avg_winner_total"]
        group = (
            wc["group_match_outcome"]
            + wc["group_match_exact"]
            + wc["group_match_rarity"]
            + wc["group_position"]
        )
        knockout = (
            wc["knockout_match_outcome"] + wc["knockout_match_exact"] + wc["knockout_match_rarity"]
        )
        bracket = wc["r32"] + wc["r16"] + wc["qf"] + wc["sf"] + wc["final"] + wc["winner"]
        bonus = wc["bonus"]
        exact = wc["group_match_exact"] + wc["knockout_match_exact"]
        rarity = wc["group_match_rarity"] + wc["knockout_match_rarity"]

        def pc(part):
            return f"{100*part/total:.0f}%" if total > 0 else "—"

        row = [
            label,
            f"{total:.0f}",
            f"{agg['pct_winner_picked_champion']:.0f}%",
            f"{agg['corr_skill_vs_rank']:.2f}",
            pc(group),
            pc(knockout),
            pc(bracket),
            pc(bonus),
            pc(exact),
            pc(rarity),
        ]
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Detailed breakdown per variant")
    lines.append("")

    for label, agg in results:
        wc = agg["winner_components"]
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"- avg winner total: **{agg['avg_winner_total']:.0f} pts**")
        lines.append(f"- avg winner skill: {agg['avg_winner_skill']:.2f}")
        lines.append(f"- % tournaments where winner picked the actual champion: **{agg['pct_winner_picked_champion']:.0f}%**")
        lines.append(f"- skill-vs-rank correlation: {agg['corr_skill_vs_rank']:.2f}")
        lines.append("")
        lines.append("Winner's avg points by source:")
        lines.append("")
        lines.append("| source | avg pts |")
        lines.append("|---|---:|")
        for k, v in wc.items():
            lines.append(f"| {k} | {v:.0f} |")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournaments", type=int, default=300, help="Monte Carlo runs")
    parser.add_argument("--predictors", type=int, default=30, help="Predictors per tournament")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        type=Path,
        # Default to backend/scripts/ since that's mounted into the dev
        # container (BACKEND_DIR.parent maps to '/' inside the container,
        # which has no host mount). The user can move/symlink to docs/ if
        # they want it versioned alongside the other scoring docs.
        default=SCRIPT_DIR / "scoring-calibration-report.md",
        help="Path to write the markdown report.",
    )
    args = parser.parse_args()

    base_rng = random.Random(args.seed)

    variants = all_variants()
    results: list[tuple[str, dict[str, Any]]] = []

    for label, config in variants:
        rng = random.Random(args.seed)  # same tournament seed across variants
        predictors = build_predictors(args.predictors, rng)

        run = SimRun(config=config, label=label)
        for _ in range(args.tournaments):
            scores, _ = simulate_one(predictors, rng, config)
            run.tournaments.append(scores)

        agg = aggregate_run(run)
        results.append((label, agg))

        # Terse stdout line per variant.
        wc = agg["winner_components"]
        total = agg["avg_winner_total"]
        group = (
            wc["group_match_outcome"]
            + wc["group_match_exact"]
            + wc["group_match_rarity"]
            + wc["group_position"]
        )
        bracket = wc["r32"] + wc["r16"] + wc["qf"] + wc["sf"] + wc["final"] + wc["winner"]
        print(
            f"{label:<48s} winner={total:.0f}pts "
            f"champ={agg['pct_winner_picked_champion']:.0f}% "
            f"corr={agg['corr_skill_vs_rank']:.2f} "
            f"group={100*group/total:.0f}% (pos={wc['group_position']:.0f}) "
            f"bracket={100*bracket/total:.0f}%"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(results, args.tournaments, args.predictors))
    print(f"\nMarkdown report → {args.output}")


if __name__ == "__main__":
    main()

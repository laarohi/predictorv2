"""Pure pick-construction logic for the ghost entrants (no DB, no I/O).

Used by scripts/seed_ghosts.py to build the wisdom-of-the-crowd and
Polymarket ghosts' Phase-1 prediction sets, and unit-tested directly in
tests/test_ghost_picks.py.

The FIFA 2026 knockout structure below is a Python port of
frontend/src/lib/config/bracketConfig.ts (R32 seed slots + progression)
plus the official third-place allocation grid, which is read from
scripts/data/third_place_mapping.json — a verbatim copy of
frontend/src/lib/config/thirdPlaceMapping.json. Both are static FIFA
tournament data; if one side ever changes, change the other (same rule
as the standings golden-parity tests).
"""

from __future__ import annotations

import json
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"

# ---------------------------------------------------------------------------
# FIFA 2026 bracket structure
# ---------------------------------------------------------------------------

# R32 matches 73-88. Each side is either a direct group position ("1A",
# "2B") or a third-place slot, denoted "T" — resolved via the allocation
# grid keyed by THIS match's winner-key (the group-winner position it is
# paired with, per bracketResolver's MATCH_TO_WINNER_KEY).
R32_SEEDS: dict[int, tuple[str, str]] = {
    73: ("2A", "2B"),
    74: ("1E", "T"),
    75: ("1F", "2C"),
    76: ("1C", "2F"),
    77: ("1I", "T"),
    78: ("2E", "2I"),
    79: ("1A", "T"),
    80: ("1L", "T"),
    81: ("1D", "T"),
    82: ("1G", "T"),
    83: ("2K", "2L"),
    84: ("1H", "2J"),
    85: ("1B", "T"),
    86: ("1J", "2H"),
    87: ("1K", "T"),
    88: ("2D", "2G"),
}

# Third-place slot key per R32 match (bracketResolver MATCH_TO_WINNER_KEY).
THIRD_SLOT_KEY: dict[int, str] = {
    74: "1E",
    77: "1I",
    79: "1A",
    80: "1L",
    81: "1D",
    82: "1G",
    85: "1B",
    87: "1K",
}

# Later rounds: match -> (home feeder match, away feeder match).
R16_FEEDS: dict[int, tuple[int, int]] = {
    89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
    93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87),
}
QF_FEEDS: dict[int, tuple[int, int]] = {97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96)}
SF_FEEDS: dict[int, tuple[int, int]] = {101: (97, 98), 102: (99, 100)}
FINAL_FEEDS: dict[int, tuple[int, int]] = {104: (101, 102)}

# Winner of a match in round k advances INTO this stage — the stage whose
# support numbers decide the pick.
ROUND_ORDER = ["round_of_32", "round_of_16", "quarter_final", "semi_final", "final", "winner"]


def load_third_place_mapping() -> dict[str, dict[str, str]]:
    with open(_DATA_DIR / "third_place_mapping.json") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Modal (mode-answer) helpers
# ---------------------------------------------------------------------------


def outcome_of(h: int, a: int) -> str:
    return "1" if h > a else "2" if a > h else "X"


def modal_score(counts: dict[tuple[int, int], int]) -> tuple[int, int]:
    """The crowd's score for one match: modal outcome first, then the modal
    scoreline within that outcome.

    Tie-breaks (fully deterministic):
    - outcome: more picks > contains the single most-picked scoreline >
      home win > draw > away win (favours the conventional reading).
    - scoreline within the outcome: more picks > fewer total goals >
      lower home score.
    """
    if not counts:
        raise ValueError("no predictions to take a mode over")

    by_outcome: dict[str, int] = {"1": 0, "X": 0, "2": 0}
    best_line_in: dict[str, int] = {"1": 0, "X": 0, "2": 0}
    for (h, a), n in counts.items():
        o = outcome_of(h, a)
        by_outcome[o] += n
        best_line_in[o] = max(best_line_in[o], n)

    outcome_rank = {"1": 0, "X": 1, "2": 2}
    outcome = min(
        by_outcome,
        key=lambda o: (-by_outcome[o], -best_line_in[o], outcome_rank[o]),
    )

    lines = [(score, n) for score, n in counts.items() if outcome_of(*score) == outcome]
    (h, a), _ = min(lines, key=lambda kv: (-kv[1], kv[0][0] + kv[0][1], kv[0][0]))
    return (h, a)


def modal_answer(counts: dict[str, int]) -> str:
    """Most-picked answer; ties broken case-insensitively alphabetically."""
    if not counts:
        raise ValueError("no answers to take a mode over")
    return min(counts, key=lambda a: (-counts[a], a.casefold()))


# ---------------------------------------------------------------------------
# Legality-constrained bracket construction
# ---------------------------------------------------------------------------


def build_bracket(
    standings: dict[str, list[str]],
    qualifying_thirds: list[tuple[str, str]],
    support: "callable[[str, str], tuple]",
) -> dict[str, list[str]]:
    """Build a structurally legal Phase-1 bracket.

    Args:
        standings: predicted finishing order per group, {"A": [t1, t2, t3, t4], ...}
        qualifying_thirds: the 8 qualifying third-place (group, team) pairs
        support: support(team, stage) -> comparable key; at every bracket
            node the side with the HIGHER key advances. This is where the
            crowd counts / market probabilities come in — the constraint
            "two crowd-favourite finalists can't both reach the final if
            the bracket pairs them earlier" is enforced by construction,
            because every advance is decided one node at a time along the
            real FIFA tree.

    Returns {stage: [teams]} for the six TeamPrediction stages.
    """
    positions: dict[str, str] = {}
    for group, order in standings.items():
        positions[f"1{group}"] = order[0]
        positions[f"2{group}"] = order[1]
        positions[f"3{group}"] = order[2]

    third_groups = "".join(sorted(g for g, _t in qualifying_thirds))
    mapping = load_third_place_mapping().get(third_groups)
    if mapping is None:
        raise ValueError(f"no third-place allocation for combination {third_groups}")
    third_by_group = {g: t for g, t in qualifying_thirds}

    def resolve(spec: str, match_no: int) -> str:
        if spec == "T":
            slot_key = THIRD_SLOT_KEY[match_no]
            target = mapping[slot_key]  # e.g. "3E"
            return third_by_group[target[1:]]
        return positions[spec]

    r32_pairs: dict[int, tuple[str, str]] = {
        m: (resolve(h, m), resolve(a, m)) for m, (h, a) in R32_SEEDS.items()
    }

    winners: dict[int, str] = {}

    def play(match_no: int, home: str, away: str, into_stage: str) -> str:
        # Higher support advances; the home seed wins exact ties (support
        # keys should already end in a deterministic component).
        winner = home if support(home, into_stage) >= support(away, into_stage) else away
        winners[match_no] = winner
        return winner

    stages: dict[str, list[str]] = {s: [] for s in ROUND_ORDER}
    stages["round_of_32"] = [t for pair in r32_pairs.values() for t in pair]

    for m, (h, a) in r32_pairs.items():
        stages["round_of_16"].append(play(m, h, a, "round_of_16"))
    for stage, feeds in (
        ("quarter_final", R16_FEEDS),
        ("semi_final", QF_FEEDS),
        ("final", SF_FEEDS),
        ("winner", FINAL_FEEDS),
    ):
        for m, (fh, fa) in feeds.items():
            stages[stage].append(play(m, winners[fh], winners[fa], stage))

    expected = dict(zip(ROUND_ORDER, (32, 16, 8, 4, 2, 1)))
    for stage, n in expected.items():
        assert len(stages[stage]) == n, f"{stage}: {len(stages[stage])} != {n}"
        assert len(set(stages[stage])) == n, f"{stage}: duplicate teams"
    return stages


def derived_group_goal_answers(
    score_by_fixture: dict[tuple[str, str], tuple[int, int]],
) -> dict[str, str]:
    """Group-stage bonus answers implied by a full set of predicted scores.

    Input: {(home_team, away_team): (home_score, away_score)} for all 72
    group fixtures. Ties broken alphabetically (casefold) for determinism.
    """
    scored: dict[str, int] = {}
    conceded: dict[str, int] = {}
    for (home, away), (hs, as_) in score_by_fixture.items():
        scored[home] = scored.get(home, 0) + hs
        scored[away] = scored.get(away, 0) + as_
        conceded[home] = conceded.get(home, 0) + as_
        conceded[away] = conceded.get(away, 0) + hs

    def pick(d: dict[str, int], want_max: bool) -> str:
        sign = -1 if want_max else 1
        return min(d, key=lambda t: (sign * d[t], t.casefold()))

    return {
        "most_goals_scored_group": pick(scored, True),
        "least_goals_scored_group": pick(scored, False),
        "most_goals_conceded_group": pick(conceded, True),
        "least_goals_conceded_group": pick(conceded, False),
    }


def exit_stage_index(team: str, stages: dict[str, list[str]]) -> int:
    """How far a team goes in a bracket: -1 = out in groups, 0 = out in
    R32, ... 5 = champion (present at 'winner')."""
    idx = -1
    for i, stage in enumerate(ROUND_ORDER):
        if team in stages[stage]:
            idx = i
    return idx


def derived_dark_horse(
    stages: dict[str, list[str]],
    fifa_ranks: dict[str, int],
    cutoff_rank: int = 12,
) -> str | None:
    """Team OUTSIDE the FIFA top `cutoff_rank` progressing furthest in the
    bracket. Ties: worse FIFA rank first (the darker horse), then name."""
    eligible = [t for t in stages["round_of_32"] if fifa_ranks.get(t, 999) > cutoff_rank]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda t: (-exit_stage_index(t, stages), -fifa_ranks.get(t, 999), t.casefold()),
    )


def derived_flop(
    all_teams: list[str],
    stages: dict[str, list[str]],
    fifa_ranks: dict[str, int],
    cutoff_rank: int = 7,
) -> str | None:
    """Team INSIDE the FIFA top `cutoff_rank` eliminated earliest. Ties:
    better FIFA rank first (the bigger bottler), then name."""
    eligible = [t for t in all_teams if fifa_ranks.get(t, 999) <= cutoff_rank]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda t: (exit_stage_index(t, stages), fifa_ranks.get(t, 999), t.casefold()),
    )

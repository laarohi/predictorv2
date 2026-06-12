"""Unit tests for scripts/ghost_lib.py — the pure pick-construction logic
behind the ghost entrants (modal answers + legality-constrained bracket).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ghost_lib import (  # noqa: E402
    R32_SEEDS,
    ROUND_ORDER,
    build_bracket,
    derived_dark_horse,
    derived_flop,
    derived_group_goal_answers,
    modal_answer,
    modal_score,
)

GROUPS = "ABCDEFGHIJKL"


def _standings():
    """Synthetic predicted order: group X finishes X1, X2, X3, X4."""
    return {g: [f"{g}1", f"{g}2", f"{g}3", f"{g}4"] for g in GROUPS}


def _thirds(groups="ABCDEFGH"):
    return [(g, f"{g}3") for g in groups]


class TestModalScore:
    def test_plain_mode(self):
        assert modal_score({(2, 1): 5, (1, 0): 3}) == (2, 1)

    def test_outcome_majority_beats_scoreline_plurality(self):
        # 3 picks of 0-1 (away) vs 4 home-win picks split 2/2: the crowd
        # leans home, so the answer must be a home score, not 0-1.
        counts = {(1, 0): 2, (2, 1): 2, (0, 1): 3}
        assert modal_score(counts) == (1, 0)  # fewer total goals breaks the tie

    def test_within_outcome_tiebreak_prefers_fewer_goals_then_lower_home(self):
        assert modal_score({(3, 1): 2, (2, 0): 2}) == (2, 0)
        assert modal_score({(2, 2): 1, (1, 1): 1, (0, 0): 1}) == (0, 0)


class TestModalAnswer:
    def test_mode(self):
        assert modal_answer({"France": 5, "Spain": 3}) == "France"

    def test_tie_alphabetical_casefold(self):
        assert modal_answer({"spain": 2, "France": 2}) == "France"


class TestBuildBracket:
    def test_sizes_and_stage_chain(self):
        support = lambda team, stage: (0,)  # noqa: E731 — home seed wins everything
        stages = build_bracket(_standings(), _thirds(), support)
        sizes = {s: len(stages[s]) for s in ROUND_ORDER}
        assert sizes == {
            "round_of_32": 32, "round_of_16": 16, "quarter_final": 8,
            "semi_final": 4, "final": 2, "winner": 1,
        }
        for later, earlier in zip(ROUND_ORDER[1:], ROUND_ORDER[:-1]):
            assert set(stages[later]) <= set(stages[earlier])

    def test_r32_roster_is_qualifiers(self):
        stages = build_bracket(_standings(), _thirds(), lambda t, s: (0,))
        expected = {f"{g}1" for g in GROUPS} | {f"{g}2" for g in GROUPS} | {
            f"{g}3" for g in "ABCDEFGH"
        }
        assert set(stages["round_of_32"]) == expected

    def test_higher_support_advances(self):
        # B2 has more R16 support than A2 — match 73 is 2A vs 2B.
        support = lambda t, s: (1,) if t == "B2" else (0,)  # noqa: E731
        stages = build_bracket(_standings(), _thirds(), support)
        assert "B2" in stages["round_of_16"]
        assert "A2" not in stages["round_of_16"]

    def test_two_favourites_in_same_path_cannot_both_reach_the_final(self):
        # Give the two teams of R32 match 73 (A2, B2) overwhelming support
        # at EVERY stage — the naive mode would put both in the final, but
        # they meet in the round of 32, so exactly one may survive.
        support = lambda t, s: (10,) if t in ("A2", "B2") else (0,)  # noqa: E731
        stages = build_bracket(_standings(), _thirds(), support)
        survivors = {t for t in ("A2", "B2") if t in stages["round_of_16"]}
        assert len(survivors) == 1
        finalists = set(stages["final"])
        assert ("A2" in finalists) ^ ("B2" in finalists)

    def test_r16_winner_comes_from_the_right_pairing(self):
        stages = build_bracket(_standings(), _thirds(), lambda t, s: (0,))
        # Every R16 entrant must come from its own R32 match, in order.
        positions = {f"1{g}": f"{g}1" for g in GROUPS}
        positions.update({f"2{g}": f"{g}2" for g in GROUPS})
        for i, (m, (h, a)) in enumerate(R32_SEEDS.items()):
            entrant = stages["round_of_16"][i]
            allowed = {positions.get(h), positions.get(a)} | {
                f"{g}3" for g in "ABCDEFGH"
            }
            assert entrant in allowed, f"match {m}: {entrant} not from {h}/{a}"


class TestDerivedBonus:
    def test_group_goal_answers(self):
        scores = {
            ("X", "Y"): (3, 0),
            ("Y", "Z"): (1, 1),
            ("X", "Z"): (2, 2),
        }
        ans = derived_group_goal_answers(scores)
        assert ans["most_goals_scored_group"] == "X"  # 5 scored
        assert ans["least_goals_scored_group"] == "Y"  # 2 scored
        assert ans["most_goals_conceded_group"] == "Y"  # 4 conceded
        assert ans["least_goals_conceded_group"] == "X"  # 2 conceded

    def test_dark_horse_and_flop(self):
        stages = {s: [] for s in ROUND_ORDER}
        stages["round_of_32"] = ["Big1", "Big2", "Mid", "Small"]
        stages["round_of_16"] = ["Big1", "Small"]
        stages["quarter_final"] = ["Small"]
        ranks = {"Big1": 1, "Big2": 3, "Mid": 10, "Small": 30}
        # Small (rank 30, outside top 12) goes furthest of the outsiders.
        assert derived_dark_horse(stages, ranks) == "Small"
        # Big2 (rank 3, inside top 7) is out in the R32 — earliest exit.
        assert derived_flop(["Big1", "Big2", "Mid", "Small"], stages, ranks) == "Big2"

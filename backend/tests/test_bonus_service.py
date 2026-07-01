"""Unit tests for bonus-question scoring helpers.

These are pure-function tests — no DB fixtures needed. The full
calculate_bonus_points() path is covered indirectly by the leaderboard
integration tests; here we just nail down the comparison semantics
and the auto-resolver math.
"""

from types import SimpleNamespace

from app.models.fixture import MatchStatus
from app.services.bonus import (
    answer_in,
    answers_match,
    bonus_question_title,
    compute_bottlers,
    compute_dark_horse,
    compute_group_stats,
    compute_team_progress,
)


def _fx(home, away, stage, *, home_score=None, away_score=None, status=MatchStatus.FINISHED):
    """Build a fixture-like SimpleNamespace for the compute tests. Avoids
    DB setup; the compute functions only read the fields we set here."""
    score = (
        SimpleNamespace(
            home_score=home_score,
            away_score=away_score,
            outcome=("1" if home_score > away_score else "2" if away_score > home_score else "X"),
        )
        if home_score is not None and away_score is not None
        else None
    )
    return SimpleNamespace(
        home_team=home, away_team=away, stage=stage, status=status, score=score
    )


class TestAnswersMatch:
    def test_exact(self):
        assert answers_match("Germany", "Germany")

    def test_case_insensitive(self):
        assert answers_match("germany", "GERMANY")

    def test_accent_insensitive(self):
        assert answers_match("Mbappé", "Mbappe")

    def test_whitespace_trimmed(self):
        assert answers_match("  Spain  ", "Spain")

    def test_different(self):
        assert not answers_match("Spain", "Germany")

    def test_empty_user(self):
        assert not answers_match("", "Germany")


class TestAnswerIn:
    """The multi-answer matcher — used when a bonus question has tied
    correct answers (e.g. two teams scoring the same number of goals)."""

    def test_match_first(self):
        assert answer_in("Germany", ["Germany", "Spain"])

    def test_match_later(self):
        assert answer_in("Spain", ["Germany", "Spain", "France"])

    def test_case_insensitive(self):
        assert answer_in("germany", ["GERMANY", "Spain"])

    def test_accent_insensitive(self):
        assert answer_in("Mbappé", ["Mbappe", "Haaland"])

    def test_no_match(self):
        assert not answer_in("Italy", ["Germany", "Spain"])

    def test_empty_user_answer(self):
        # An empty user prediction must never score, even against a
        # non-empty correct-answer list.
        assert not answer_in("", ["Germany"])

    def test_empty_correct_list(self):
        # An unresolved question (no stored correct answers) must never
        # award points.
        assert not answer_in("Germany", [])


class TestBonusQuestionTitle:
    """The short title shown in the standings breakdown panel — drops the
    ' — description' clause that the wizard/admin UI still needs in full."""

    def test_strips_description(self):
        assert bonus_question_title(
            "The Fortress — team that conceded the fewest goals in the group stage"
        ) == "The Fortress"

    def test_no_dash_returns_unchanged(self):
        assert bonus_question_title("Golden Ball") == "Golden Ball"


class TestComputeGroupStats:
    def test_aggregates_goals_for_and_against(self):
        fixtures = [
            _fx("Germany", "Italy", "group", home_score=3, away_score=1),
            _fx("Italy", "Spain", "group", home_score=0, away_score=2),
            _fx("Spain", "Germany", "group", home_score=1, away_score=1),
        ]
        stats = compute_group_stats(fixtures)
        assert stats["Germany"] == {"gf": 4, "ga": 2}
        assert stats["Italy"] == {"gf": 1, "ga": 5}
        assert stats["Spain"] == {"gf": 3, "ga": 1}

    def test_ignores_non_group_stages(self):
        fixtures = [
            _fx("Germany", "Italy", "group", home_score=3, away_score=0),
            _fx("Germany", "Spain", "quarter_final", home_score=99, away_score=0),
        ]
        stats = compute_group_stats(fixtures)
        # The knockout 99-0 must not pollute group totals.
        assert stats["Germany"]["gf"] == 3

    def test_ignores_unfinished_or_unscored(self):
        fixtures = [
            _fx("Germany", "Italy", "group", home_score=3, away_score=1),
            _fx("Spain", "France", "group", status=MatchStatus.SCHEDULED),
            _fx("Brazil", "Argentina", "group", home_score=2, away_score=1, status=MatchStatus.LIVE),
        ]
        stats = compute_group_stats(fixtures)
        assert set(stats.keys()) == {"Germany", "Italy"}

    def test_ignores_tbd_teams(self):
        fixtures = [
            _fx("TBD", "Italy", "group", home_score=0, away_score=0),
            _fx("Germany", "TBD", "group", home_score=2, away_score=1),
        ]
        stats = compute_group_stats(fixtures)
        # Neither row contributes since each has a TBD placeholder.
        assert stats == {}


class TestComputeTeamProgress:
    def test_furthest_stage_per_team(self):
        fixtures = [
            _fx("Germany", "Italy", "group", home_score=1, away_score=0),
            _fx("Germany", "Spain", "round_of_32", home_score=2, away_score=1),
            _fx("Germany", "France", "round_of_16", home_score=0, away_score=1),
        ]
        progress = compute_team_progress(fixtures)
        # Germany reached R16, France advanced (only appears at R16 here),
        # Italy and Spain stayed at group / R32.
        assert progress["Germany"] == "round_of_16"
        assert progress["France"] == "round_of_16"
        assert progress["Italy"] == "group"
        assert progress["Spain"] == "round_of_32"

    def test_final_winner_marked(self):
        fixtures = [
            _fx("Germany", "France", "final", home_score=2, away_score=1),
        ]
        progress = compute_team_progress(fixtures)
        assert progress["Germany"] == "winner"
        assert progress["France"] == "final"

    def test_unfinished_final_no_winner(self):
        fixtures = [
            _fx("Germany", "France", "final", status=MatchStatus.SCHEDULED),
        ]
        progress = compute_team_progress(fixtures)
        # Neither team gets credited until the match finishes.
        assert progress == {}


class TestComputeDarkHorse:
    def test_picks_furthest_outside_top_n(self):
        # Germany (top) reaches semi, Morocco (not top) reaches quarter.
        # Spain (top) reaches final. Dark horse = Morocco.
        progress = {
            "Germany": "semi_final",
            "Spain": "final",
            "Morocco": "quarter_final",
            "Italy": "group",
        }
        fifa_top = {"Germany", "Spain"}
        assert compute_dark_horse(progress, fifa_top) == ["Morocco"]

    def test_ties_alphabetical(self):
        progress = {
            "Morocco": "quarter_final",
            "Senegal": "quarter_final",
            "Spain": "final",  # top, ignored
        }
        fifa_top = {"Spain"}
        assert compute_dark_horse(progress, fifa_top) == ["Morocco", "Senegal"]

    def test_no_non_top_teams_returns_empty(self):
        progress = {"Germany": "final", "Spain": "final"}
        fifa_top = {"Germany", "Spain"}
        assert compute_dark_horse(progress, fifa_top) == []

    def test_winning_underdog_outranks_top_finalist(self):
        # Morocco wins the final against Germany — Morocco is dark horse.
        progress = {"Morocco": "winner", "Germany": "final"}
        fifa_top = {"Germany"}
        assert compute_dark_horse(progress, fifa_top) == ["Morocco"]


class TestComputeBottlers:
    def test_earliest_exit_among_top(self):
        progress = {
            "Germany": "group",      # eliminated in group — bottle
            "Spain": "round_of_16",  # made it to R16
            "France": "quarter_final",
            "Italy": "group",        # also eliminated in group
        }
        fifa_top = {"Germany", "Spain", "France", "Italy"}
        all_teams = {"Germany", "Spain", "France", "Italy", "Morocco"}
        assert compute_bottlers(progress, fifa_top, all_teams) == ["Germany", "Italy"]

    def test_ignores_top_teams_not_in_competition(self):
        # Croatia is in the top list but didn't even enter the tournament —
        # they can't be the bottlers.
        progress = {"Germany": "group"}
        fifa_top = {"Germany", "Croatia"}
        all_teams = {"Germany"}
        assert compute_bottlers(progress, fifa_top, all_teams) == ["Germany"]

    def test_excludes_winner(self):
        # If the only top team won, they're not the bottlers (and no one
        # else is in the top list).
        progress = {"Germany": "winner"}
        fifa_top = {"Germany"}
        all_teams = {"Germany"}
        assert compute_bottlers(progress, fifa_top, all_teams) == []

    def test_top_team_with_no_data_treated_as_group(self):
        # If a top team has no finished fixtures, they're presumed still
        # in group — earliest possible exit. This is fine: pre-tournament
        # the function returns all top teams as "tied bottlers" which is
        # the admin's signal to wait until matches are played.
        progress = {}
        fifa_top = {"Germany", "Spain"}
        all_teams = {"Germany", "Spain"}
        assert compute_bottlers(progress, fifa_top, all_teams) == ["Germany", "Spain"]

"""Tests for the group-standings service.

Covers get_actual_group_standings (W/D/L counts, tie-breakers, partial groups),
get_group_positions (1A..4L position encoding), and
get_qualifying_third_place_teams (top 8 of 12 best 3rd-placed teams).

These three functions decide who advances from groups and where they
slot into the knockout bracket — the highest-stakes correctness path
in the app. Per CLAUDE.md "Scoring Engine Safety": no logic changes
without a corresponding test.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score, ScoreSource
from app.models.user import User
from app.services.scoring import calculate_user_points, get_actual_advancement
from app.services.standings import (
    get_actual_group_standings,
    get_actual_group_standings_with_warnings,
    get_group_positions,
    get_qualifying_third_place_teams,
    get_qualifying_third_place_teams_with_warnings,
)


# Use a fixed kickoff to avoid the test depending on wall-clock time.
KICKOFF = datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Per-test in-memory SQLite session. Mirrors test_score_sync.py pattern."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(session: AsyncSession) -> Competition:
    comp = Competition(name="WC2026", entry_fee=Decimal("0"), external_id="WC")
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


def _add_match(
    session: AsyncSession,
    competition_id: UUID,
    *,
    home: str,
    away: str,
    home_score: int,
    away_score: int,
    group: str = "A",
    status: MatchStatus = MatchStatus.FINISHED,
) -> Fixture:
    """Add one finished group-stage match with a score row. Returns the fixture."""
    fixture = Fixture(
        competition_id=competition_id,
        home_team=home,
        away_team=away,
        kickoff=KICKOFF,
        stage="group",
        group=group,
        status=status,
    )
    session.add(fixture)
    session.add(
        Score(
            fixture=fixture,
            home_score=home_score,
            away_score=away_score,
            source=ScoreSource.API,
        )
    )
    return fixture


# ---------------------------------------------------------------------------
# get_actual_group_standings — basic mechanics
# ---------------------------------------------------------------------------


async def test_empty_db_returns_empty(session, competition) -> None:
    assert await get_actual_group_standings(session) == {}


async def test_single_match_creates_two_standings_rows(session, competition) -> None:
    _add_match(session, competition.id, home="France", away="Germany", home_score=2, away_score=1)
    await session.commit()

    standings = await get_actual_group_standings(session)
    teams_by_name = {t["team"]: t for t in standings["A"]}

    assert teams_by_name["France"]["won"] == 1
    assert teams_by_name["France"]["lost"] == 0
    assert teams_by_name["France"]["points"] == 3
    assert teams_by_name["France"]["goals_for"] == 2
    assert teams_by_name["France"]["goals_against"] == 1
    assert teams_by_name["France"]["goal_difference"] == 1

    assert teams_by_name["Germany"]["won"] == 0
    assert teams_by_name["Germany"]["lost"] == 1
    assert teams_by_name["Germany"]["points"] == 0


async def test_draw_awards_one_point_each(session, competition) -> None:
    _add_match(session, competition.id, home="France", away="Germany", home_score=1, away_score=1)
    await session.commit()

    standings = await get_actual_group_standings(session)
    teams = {t["team"]: t for t in standings["A"]}
    assert teams["France"]["drawn"] == 1
    assert teams["France"]["points"] == 1
    assert teams["Germany"]["drawn"] == 1
    assert teams["Germany"]["points"] == 1


async def test_full_group_of_four_six_matches(session, competition) -> None:
    """France wins all 3, Germany wins 2, Spain wins 1, Italy loses all 3."""
    _add_match(session, competition.id, home="France", away="Germany", home_score=2, away_score=1)
    _add_match(session, competition.id, home="France", away="Spain", home_score=3, away_score=0)
    _add_match(session, competition.id, home="France", away="Italy", home_score=1, away_score=0)
    _add_match(session, competition.id, home="Germany", away="Spain", home_score=2, away_score=1)
    _add_match(session, competition.id, home="Germany", away="Italy", home_score=2, away_score=1)
    _add_match(session, competition.id, home="Spain", away="Italy", home_score=1, away_score=0)
    await session.commit()

    standings = await get_actual_group_standings(session)
    names = [t["team"] for t in standings["A"]]
    points = [t["points"] for t in standings["A"]]
    played = [t["played"] for t in standings["A"]]

    assert names == ["France", "Germany", "Spain", "Italy"]
    assert points == [9, 6, 3, 0]
    assert played == [3, 3, 3, 3]


# ---------------------------------------------------------------------------
# Sort order / tiebreakers
# ---------------------------------------------------------------------------


async def test_goal_difference_tiebreaker(session, competition) -> None:
    """Same points → higher goal difference wins.

    France and Germany both win 2/2 (= 6 pts each).
    France's wins: 3-0, 2-0  → GF 5, GA 0, GD +5
    Germany's wins: 1-0, 1-0 → GF 2, GA 0, GD +2
    France must sort above Germany.
    """
    _add_match(session, competition.id, home="France", away="Spain", home_score=3, away_score=0)
    _add_match(session, competition.id, home="France", away="Italy", home_score=2, away_score=0)
    _add_match(session, competition.id, home="Germany", away="Spain", home_score=1, away_score=0)
    _add_match(session, competition.id, home="Germany", away="Italy", home_score=1, away_score=0)
    await session.commit()

    standings = await get_actual_group_standings(session)
    names = [t["team"] for t in standings["A"]]
    assert names.index("France") < names.index("Germany")


async def test_goals_for_tiebreaker_after_gd(session, competition) -> None:
    """Same points + same GD → higher goals-for wins.

    France: 3-1, 1-0 → 6 pts, GF 4, GA 1, GD +3
    Germany: 2-0, 1-0 → 6 pts, GF 3, GA 0, GD +3
    Same GD → France wins on goals-for (4 > 3).
    """
    _add_match(session, competition.id, home="France", away="Spain", home_score=3, away_score=1)
    _add_match(session, competition.id, home="France", away="Italy", home_score=1, away_score=0)
    _add_match(session, competition.id, home="Germany", away="Spain", home_score=2, away_score=0)
    _add_match(session, competition.id, home="Germany", away="Italy", home_score=1, away_score=0)
    await session.commit()

    standings = await get_actual_group_standings(session)
    names = [t["team"] for t in standings["A"]]
    assert names.index("France") < names.index("Germany")


# Note: a "two-team H2H separation" can't be constructed from a 4-team
# round-robin — the H2H result spills into total stats and breaks the
# overall tie at step 1 already. So 2-way H2H separation is structurally
# absent from the FIFA-chain test surface. The 3-way separations *are*
# constructable but require synthetic standings rather than real matches;
# they're covered by direct unit tests on the helper (test_apply_fifa_*)
# below.


async def test_alphabetical_fallback_when_all_equal_with_warning(session, competition) -> None:
    """All four teams draw 0-0 with each other → identical stats AND identical H2H.

    The FIFA chain runs through points (3 each) → GD (0 each) → GF (0 each)
    → H2H points (3 each) → H2H GD (0 each) → H2H goals (0 each) →
    *alphabetical with warning*.
    """
    _add_match(session, competition.id, home="Argentina", away="Belgium", home_score=0, away_score=0)
    _add_match(session, competition.id, home="Argentina", away="Croatia", home_score=0, away_score=0)
    _add_match(session, competition.id, home="Argentina", away="Denmark", home_score=0, away_score=0)
    _add_match(session, competition.id, home="Belgium", away="Croatia", home_score=0, away_score=0)
    _add_match(session, competition.id, home="Belgium", away="Denmark", home_score=0, away_score=0)
    _add_match(session, competition.id, home="Croatia", away="Denmark", home_score=0, away_score=0)
    await session.commit()

    standings, warnings = await get_actual_group_standings_with_warnings(session)
    assert [t["team"] for t in standings["A"]] == ["Argentina", "Belgium", "Croatia", "Denmark"]

    # Exactly one warning naming all four teams in group A
    assert len(warnings) == 1
    assert warnings[0]["group"] == "A"
    assert warnings[0]["context"] == "group_standings"
    assert warnings[0]["tied_teams"] == ["Argentina", "Belgium", "Croatia", "Denmark"]


async def test_head_to_head_separates_when_overall_tie_includes_a_draw_h2h(
    session, competition
) -> None:
    """A pair of teams tied on overall (points, GD, GF) due to a draw H2H —
    after H2H step (also tied), fall to alphabetical and emit a warning.

    France draws Germany 1-1; both beat Spain 2-0 and beat Italy 1-0.
      - France: D + W + W = 7 pts; GF=4 GA=1 GD=+3
      - Germany: D + W + W = 7 pts; GF=4 GA=1 GD=+3
    H2H: 1-1 draw → both gain 1 H2H pt, 1 H2H goal, 0 H2H GD. Identical.
    → falls to alphabetical, France before Germany, with a warning.
    """
    _add_match(session, competition.id, home="France", away="Germany", home_score=1, away_score=1)
    _add_match(session, competition.id, home="France", away="Spain", home_score=2, away_score=0)
    _add_match(session, competition.id, home="France", away="Italy", home_score=1, away_score=0)
    _add_match(session, competition.id, home="Germany", away="Spain", home_score=2, away_score=0)
    _add_match(session, competition.id, home="Germany", away="Italy", home_score=1, away_score=0)
    _add_match(session, competition.id, home="Spain", away="Italy", home_score=1, away_score=0)
    await session.commit()

    standings, warnings = await get_actual_group_standings_with_warnings(session)
    top_two = [t["team"] for t in standings["A"][:2]]
    assert top_two == ["France", "Germany"]

    # Warning fires for the France-Germany tie
    tied_warning = next((w for w in warnings if set(w["tied_teams"]) == {"France", "Germany"}), None)
    assert tied_warning is not None, f"expected France/Germany warning, got {warnings}"
    assert tied_warning["context"] == "group_standings"


async def test_no_warning_when_clean_ranking(session, competition) -> None:
    """A clean group with no ties → no warnings produced."""
    _add_match(session, competition.id, home="France", away="Germany", home_score=2, away_score=1)
    _add_match(session, competition.id, home="France", away="Spain", home_score=3, away_score=0)
    _add_match(session, competition.id, home="France", away="Italy", home_score=1, away_score=0)
    _add_match(session, competition.id, home="Germany", away="Spain", home_score=2, away_score=1)
    _add_match(session, competition.id, home="Germany", away="Italy", home_score=2, away_score=1)
    _add_match(session, competition.id, home="Spain", away="Italy", home_score=1, away_score=0)
    await session.commit()

    _standings, warnings = await get_actual_group_standings_with_warnings(session)
    assert warnings == []


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


async def test_partial_group_does_not_crash(session, competition) -> None:
    """Only 1 of 6 matches finished — still returns sane partial standings."""
    _add_match(session, competition.id, home="France", away="Germany", home_score=2, away_score=1)
    await session.commit()

    standings = await get_actual_group_standings(session)
    teams = {t["team"]: t for t in standings["A"]}
    assert teams["France"]["played"] == 1
    assert teams["Germany"]["played"] == 1
    assert "Spain" not in teams  # untouched


async def test_ignores_unfinished_fixtures(session, competition) -> None:
    """SCHEDULED / LIVE fixtures must not pollute the standings."""
    _add_match(
        session, competition.id,
        home="France", away="Germany", home_score=2, away_score=1,
        status=MatchStatus.LIVE,
    )
    _add_match(session, competition.id, home="Spain", away="Italy", home_score=1, away_score=0)
    await session.commit()

    standings = await get_actual_group_standings(session)
    teams = {t["team"] for t in standings.get("A", [])}
    assert "France" not in teams  # LIVE — should be ignored
    assert "Spain" in teams       # FINISHED — counted


async def test_ignores_non_group_fixtures(session, competition) -> None:
    """Knockout fixtures (stage != 'group') must not enter the group standings."""
    ko = Fixture(
        competition_id=competition.id,
        home_team="France", away_team="Germany",
        kickoff=KICKOFF, stage="round_of_16", group=None,
        status=MatchStatus.FINISHED,
    )
    session.add(ko)
    session.add(Score(fixture=ko, home_score=2, away_score=1, source=ScoreSource.API))
    _add_match(session, competition.id, home="Spain", away="Italy", home_score=1, away_score=0)
    await session.commit()

    standings = await get_actual_group_standings(session)
    teams = {t["team"] for t in standings.get("A", [])}
    assert "France" not in teams
    assert "Spain" in teams


async def test_multiple_groups_kept_separate(session, competition) -> None:
    _add_match(session, competition.id, home="France", away="Germany", home_score=1, away_score=0, group="A")
    _add_match(session, competition.id, home="Spain", away="Italy", home_score=2, away_score=1, group="B")
    await session.commit()

    standings = await get_actual_group_standings(session)
    assert set(standings.keys()) == {"A", "B"}
    a_teams = {t["team"] for t in standings["A"]}
    b_teams = {t["team"] for t in standings["B"]}
    assert a_teams == {"France", "Germany"}
    assert b_teams == {"Spain", "Italy"}


# ---------------------------------------------------------------------------
# get_group_positions
# ---------------------------------------------------------------------------


async def test_group_positions_uses_1A_to_4A_encoding(session, competition) -> None:
    """Position codes encode '<position><group>'. France first in group A → '1A'."""
    _add_match(session, competition.id, home="France", away="Germany", home_score=2, away_score=1)
    _add_match(session, competition.id, home="France", away="Spain", home_score=3, away_score=0)
    _add_match(session, competition.id, home="France", away="Italy", home_score=1, away_score=0)
    _add_match(session, competition.id, home="Germany", away="Spain", home_score=2, away_score=1)
    _add_match(session, competition.id, home="Germany", away="Italy", home_score=2, away_score=1)
    _add_match(session, competition.id, home="Spain", away="Italy", home_score=1, away_score=0)
    await session.commit()

    positions = await get_group_positions(session)
    assert positions["1A"] == "France"
    assert positions["2A"] == "Germany"
    assert positions["3A"] == "Spain"
    assert positions["4A"] == "Italy"


# ---------------------------------------------------------------------------
# get_qualifying_third_place_teams
# ---------------------------------------------------------------------------


def _seed_group(
    session: AsyncSession,
    comp_id: UUID,
    group: str,
    *,
    third_place_points: int,
) -> None:
    """Seed a 4-team group so the 3rd-place finisher ends with the requested points.

    Teams are named T1{group}..T4{group}. With consistent naming, T3 always sorts
    above T4 when their stats tie (since '3' < '4' lexicographically), which makes
    the 1-pt case (both draw to share 1pt) deterministic.

    Supported third_place_points values:
      - 3  : T1 9pts, T2 6pts, T3 3pts (beats T4), T4 0pts
      - 1  : T1 9pts, T2 6pts, T3 and T4 both 1pt (drew); T3 ranks 3rd via name-sort

    A true "0pt 3rd-place" can't be expressed in a 4-team round-robin: whoever loses
    the 3rd-vs-4th match also loses everything else, and the *winner* of that match
    then has 3 pts and takes the 3rd-place slot.
    """
    t1, t2, t3, t4 = f"T1{group}", f"T2{group}", f"T3{group}", f"T4{group}"

    # T1 beats everyone (9pts)
    _add_match(session, comp_id, home=t1, away=t2, home_score=1, away_score=0, group=group)
    _add_match(session, comp_id, home=t1, away=t3, home_score=1, away_score=0, group=group)
    _add_match(session, comp_id, home=t1, away=t4, home_score=1, away_score=0, group=group)
    # T2 beats T3 and T4 (6pts)
    _add_match(session, comp_id, home=t2, away=t3, home_score=1, away_score=0, group=group)
    _add_match(session, comp_id, home=t2, away=t4, home_score=1, away_score=0, group=group)
    # T3 vs T4 decides T3's points
    if third_place_points == 3:
        _add_match(session, comp_id, home=t3, away=t4, home_score=1, away_score=0, group=group)
    elif third_place_points == 1:
        _add_match(session, comp_id, home=t3, away=t4, home_score=0, away_score=0, group=group)
    else:
        raise ValueError(
            f"unsupported third_place_points={third_place_points}; use 3 or 1 "
            "(0 is unreachable in a round-robin — see docstring)"
        )


async def test_qualifying_third_place_picks_top_8_of_12(session, competition) -> None:
    """8 groups produce a 3pt third-placed team, 4 groups produce a 1pt one.
    The top 8 must be exactly the 3pt ones."""
    for g in "ABCDEFGH":
        _seed_group(session, competition.id, g, third_place_points=3)
    for g in "IJKL":
        _seed_group(session, competition.id, g, third_place_points=1)
    await session.commit()

    top8 = await get_qualifying_third_place_teams(session)
    assert len(top8) == 8
    assert sorted(t["group"] for t in top8) == list("ABCDEFGH")


async def test_qualifying_third_place_sorts_by_points_descending(session, competition) -> None:
    """A 3pt 3rd-place team must rank above a 1pt one."""
    _seed_group(session, competition.id, "A", third_place_points=3)
    _seed_group(session, competition.id, "B", third_place_points=1)
    await session.commit()

    top8 = await get_qualifying_third_place_teams(session)
    assert [t["group"] for t in top8] == ["A", "B"]


async def test_qualifying_third_place_caps_at_8_even_if_more_groups(session, competition) -> None:
    """If all 12 groups produce a 3rd-placed team, only the top 8 are returned."""
    for g in "ABCDEFGHIJKL":
        _seed_group(session, competition.id, g, third_place_points=3)
    await session.commit()

    top8 = await get_qualifying_third_place_teams(session)
    assert len(top8) == 8


async def test_qualifying_third_place_ignores_groups_with_fewer_than_3_teams(
    session, competition
) -> None:
    """Defensive: if a group has only 2 teams (data anomaly), it shouldn't supply a 3rd-placed team."""
    _add_match(session, competition.id, home="X", away="Y", home_score=1, away_score=0, group="A")
    _seed_group(session, competition.id, "B", third_place_points=3)
    await session.commit()

    top8 = await get_qualifying_third_place_teams(session)
    # Group A has only 2 teams, no 3rd-place. Group B contributes one.
    assert [t["group"] for t in top8] == ["B"]


# ---------------------------------------------------------------------------
# FIFA tiebreaker chain — direct unit tests on the helper
# These exercise scenarios that are hard to construct via a DB-driven setup,
# particularly the 3+ way H2H mini-table separations.
# ---------------------------------------------------------------------------


from app.services.standings import _apply_fifa_tiebreakers
from datetime import timezone as _tz, datetime as _dt
from uuid import uuid4 as _uuid4


def _stand(team: str, group: str, points: int, gd: int, gf: int) -> dict:
    """Build a minimal team-standings dict matching the shape returned by to_dict()."""
    return {
        "team": team,
        "group": group,
        "played": 3,
        "won": 0,
        "drawn": 0,
        "lost": 0,
        "goals_for": gf,
        "goals_against": gf - gd,
        "goal_difference": gd,
        "points": points,
    }


def _h2h(home: str, away: str, hs: int, as_: int, group: str = "A") -> tuple[Fixture, Score]:
    """Build a (Fixture, Score) tuple for use as group_matches in the helper."""
    fid = _uuid4()
    fixture = Fixture(
        id=fid,
        competition_id=_uuid4(),
        home_team=home,
        away_team=away,
        kickoff=_dt(2026, 6, 11, 19, 0, tzinfo=_tz.utc),
        stage="group",
        group=group,
        status=MatchStatus.FINISHED,
    )
    score = Score(fixture_id=fid, home_score=hs, away_score=as_, source=ScoreSource.API)
    return fixture, score


def test_apply_fifa_tiebreakers_h2h_separates_three_way_tie() -> None:
    """Three teams tied on overall (points, GD, GF). H2H mini-table:
    A beats B, B beats C, A beats C → A=6, B=3, C=0 H2H pts.
    Overall stats are constructed so they're identical despite the H2H spread."""
    # Construct overall stats: each team plays 3 games. Assume they all faced
    # a (non-tied) 4th team and produced identical results there, plus the
    # H2H results we set up. We don't model the 4th team here; we just pass
    # standings dicts and the H2H matches.
    teams = [
        _stand("Argentina", "A", points=5, gd=0, gf=2),
        _stand("Brazil",    "A", points=5, gd=0, gf=2),
        _stand("Chile",     "A", points=5, gd=0, gf=2),
    ]
    matches = [
        _h2h("Argentina", "Brazil", 1, 0),  # A beats B
        _h2h("Brazil",    "Chile",  1, 0),  # B beats C
        _h2h("Argentina", "Chile",  1, 0),  # A beats C
    ]

    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams, group_matches=matches, context="group_standings"
    )

    # H2H: A=6pts, B=3pts, C=0pts → A first, B second, C third.
    assert [t["team"] for t in sorted_teams] == ["Argentina", "Brazil", "Chile"]
    assert warnings == []  # clean H2H ranking, no alphabetical fallback


def test_apply_fifa_tiebreakers_h2h_partially_resolves_three_way_tie() -> None:
    """Three teams tied. H2H separates one but leaves the other two tied
    on H2H → those two go alphabetical with a single warning."""
    teams = [
        _stand("Argentina", "A", points=5, gd=0, gf=2),
        _stand("Brazil",    "A", points=5, gd=0, gf=2),
        _stand("Chile",     "A", points=5, gd=0, gf=2),
    ]
    # H2H: A beats both. B and C draw with each other.
    matches = [
        _h2h("Argentina", "Brazil", 1, 0),
        _h2h("Argentina", "Chile",  1, 0),
        _h2h("Brazil",    "Chile",  0, 0),
    ]
    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams, group_matches=matches, context="group_standings"
    )
    # H2H: A=6pts, B=1pt, C=1pt → A clearly first; B and C tied on H2H → alphabetical.
    assert sorted_teams[0]["team"] == "Argentina"
    assert {sorted_teams[1]["team"], sorted_teams[2]["team"]} == {"Brazil", "Chile"}
    assert [t["team"] for t in sorted_teams[1:]] == ["Brazil", "Chile"]  # alphabetical

    # One warning, covering the B/C sub-tie
    assert len(warnings) == 1
    assert warnings[0]["tied_teams"] == ["Brazil", "Chile"]
    assert warnings[0]["context"] == "group_standings"


def test_apply_fifa_tiebreakers_no_h2h_and_no_rankings_falls_to_alphabetical() -> None:
    """When group_matches is None (cross-group sort) AND FIFA Rankings cover
    none of the tied teams, the chain falls through to alphabetical with a
    warning. Pins the last-resort behaviour."""
    teams = [
        _stand("Wales",   "A", points=3, gd=0, gf=1),
        _stand("Senegal", "B", points=3, gd=0, gf=1),
        _stand("Iran",    "C", points=3, gd=0, gf=1),
    ]
    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams,
        group_matches=None,
        context="third_place_qualifying",
        fifa_rankings=[],  # force the alphabetical fallback
    )
    assert [t["team"] for t in sorted_teams] == ["Iran", "Senegal", "Wales"]
    assert len(warnings) == 1
    assert warnings[0]["tied_teams"] == ["Iran", "Senegal", "Wales"]
    assert warnings[0]["context"] == "third_place_qualifying"


# ---------------------------------------------------------------------------
# Third-place qualifying warnings via the public *_with_warnings function
# ---------------------------------------------------------------------------


async def test_qualifying_third_place_with_warnings_at_8_9_boundary(
    session, competition
) -> None:
    """When several 3rd-placed teams tie on (points, GD, GF) across the 8/9
    boundary, the cut is alphabetical and a third_place_qualifying warning
    fires naming the tied teams."""
    # All 12 groups produce 3rd-placed teams with 3 pts, GD=-1, GF=1 (the
    # _seed_group(third_place_points=3) pattern). They differ only by group
    # letter — so the 3rd-place sort produces a 12-way overall tie and
    # alphabetical ranks T3A..T3L. Top 8 = A..H, cut at the 8/9 boundary.
    for g in "ABCDEFGHIJKL":
        _seed_group(session, competition.id, g, third_place_points=3)
    await session.commit()

    top8, warnings = await get_qualifying_third_place_teams_with_warnings(session)
    assert len(top8) == 8
    assert sorted(t["group"] for t in top8) == list("ABCDEFGH")

    # Exactly one third-place tie warning covering all 12 teams
    tp_warnings = [w for w in warnings if w["context"] == "third_place_qualifying"]
    assert len(tp_warnings) == 1
    assert len(tp_warnings[0]["tied_teams"]) == 12


# ---------------------------------------------------------------------------
# FIFA Article 13 chain — H2H priority, descent through step 2, FIFA Rankings
#
# These tests pin the *order* of the chain, which is what diverges from FIFA's
# regulations in the original implementation. The chain per Article 13:
#
#   Step 1 (only among teams equal on POINTS):
#     a) H2H points
#     b) H2H goal difference
#     c) H2H goals scored
#   Step 2 (if subset still tied):
#     re-apply a-c to the still-tied subset's mutual matches, then:
#     d) overall goal difference
#     e) overall goals scored
#     f) fair-play conduct  ← we don't track; emit warning, skip
#   Step 3:
#     g) FIFA Ranking (most recent)
#     h) FIFA Ranking (preceding editions)
#   Final fallback: alphabetical (with the warning already emitted).
# ---------------------------------------------------------------------------


def test_h2h_beats_overall_gd_when_equal_on_points() -> None:
    """Article 13 Step 1: teams equal on POINTS go to H2H BEFORE overall GD.

    Regression for the chain-ordering bug: the original implementation
    sorted by overall (points, GD, GF) first, which let a team with worse
    H2H but better padded overall GD climb above the H2H winner.

    Scenario: Argentina beat Brazil 1-0 in their direct match. Both ended
    on 6 points. Brazil ran up the score against a weaker opponent so
    has overall GD +5 vs Argentina's 0. FIFA's rule: Argentina wins the
    tie because they beat Brazil head-to-head.
    """
    teams = [
        _stand("Argentina", "A", points=6, gd=0, gf=2),
        _stand("Brazil",    "A", points=6, gd=5, gf=6),
    ]
    matches = [_h2h("Argentina", "Brazil", 1, 0)]

    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams,
        group_matches=matches,
        context="group_standings",
        fifa_rankings=["France", "Argentina", "Brazil"],
    )
    assert [t["team"] for t in sorted_teams] == ["Argentina", "Brazil"]
    # Clean H2H separation — no chain descent, no warning.
    assert warnings == []


def test_h2h_breaks_three_way_tie_even_with_asymmetric_overall_gd() -> None:
    """A 3-way tie on points where overall GD is wildly asymmetric — H2H
    is still the first criterion.

    A beat B, B beat C, A beat C. Overall GDs constructed to disagree:
    A=+1, B=+3, C=-4 (B padded against a 4th, weaker team). FIFA order
    by H2H pts: A=6, B=3, C=0 → A, B, C. Buggy chain (overall GD first)
    would give B, A, C.
    """
    teams = [
        _stand("A", "A", points=6, gd=+1, gf=4),
        _stand("B", "A", points=6, gd=+3, gf=5),
        _stand("C", "A", points=6, gd=-4, gf=1),
    ]
    matches = [
        _h2h("A", "B", 1, 0),
        _h2h("B", "C", 1, 0),
        _h2h("A", "C", 1, 0),
    ]
    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams,
        group_matches=matches,
        context="group_standings",
        fifa_rankings=[],
    )
    assert [t["team"] for t in sorted_teams] == ["A", "B", "C"]
    assert warnings == []


def test_chain_descends_to_step_2_overall_stats_when_h2h_ties() -> None:
    """When H2H steps a-c can't separate equal-on-points teams, descend
    to step 2 d (overall GD), e (overall GF), then f (fair-play, skip
    with warning), then step 3 g (FIFA Ranking).

    Scenario: A and B both 6 pts, drew 1-1 (equal H2H pts/GD/GF).
    Overall GD differs: A=+4, B=+1 → A wins on overall GD (step 2 d).
    Step 2 was reached but not exhausted — no warning required.
    """
    teams = [
        _stand("A", "A", points=6, gd=4, gf=5),
        _stand("B", "A", points=6, gd=1, gf=3),
    ]
    matches = [_h2h("A", "B", 1, 1)]
    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams,
        group_matches=matches,
        context="group_standings",
        fifa_rankings=[],
    )
    assert [t["team"] for t in sorted_teams] == ["A", "B"]
    # Step 2 d resolved it cleanly — no fair-play tier reached, no warning.
    assert warnings == []


def test_fair_play_tier_emits_warning_then_fifa_rankings_resolve() -> None:
    """When chain reaches the fair-play (conduct) criterion — which we don't
    track — emit a warning and proceed to FIFA Rankings.

    Scenario: A and B identical on H2H + overall GD + overall GF. Step 2
    f would consult fair-play; we can't, so warn. Step 3 g consults FIFA
    Rankings: "Upper" is listed above "Lower" → Upper ranks higher.
    """
    teams = [
        _stand("Lower", "A", points=6, gd=2, gf=4),
        _stand("Upper", "A", points=6, gd=2, gf=4),
    ]
    matches = [_h2h("Upper", "Lower", 1, 1)]
    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams,
        group_matches=matches,
        context="group_standings",
        fifa_rankings=["Upper", "Lower"],
    )
    assert [t["team"] for t in sorted_teams] == ["Upper", "Lower"]
    assert len(warnings) == 1
    assert warnings[0]["tied_teams"] == ["Lower", "Upper"]  # alphabetized
    assert warnings[0]["context"] == "group_standings"


def test_fifa_rankings_listed_team_ranks_above_unlisted() -> None:
    """When FIFA Rankings cover one tied team but not the other, the
    listed team ranks above. (Defensive: rankings YAML may not yet cover
    every WC qualifier; this lets the chain do something sensible until
    the rankings list is completed.)

    Non-coincidental: Aardvark sorts alphabetically BEFORE Belgium, so
    "listed ranks above unlisted" must come from rankings, not alphabetical.
    """
    teams = [
        _stand("Aardvark", "A", points=6, gd=2, gf=4),  # unlisted
        _stand("Belgium",  "A", points=6, gd=2, gf=4),  # listed
    ]
    matches = [_h2h("Aardvark", "Belgium", 1, 1)]
    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams,
        group_matches=matches,
        context="group_standings",
        fifa_rankings=["France", "Belgium"],
    )
    assert [t["team"] for t in sorted_teams] == ["Belgium", "Aardvark"]
    assert len(warnings) == 1


def test_alphabetical_fallback_when_neither_team_in_fifa_rankings() -> None:
    """Last resort: if FIFA Rankings cover neither team, fall to
    alphabetical (with the fair-play warning already emitted)."""
    teams = [
        _stand("Yankland", "A", points=6, gd=2, gf=4),
        _stand("Zedland",  "A", points=6, gd=2, gf=4),
    ]
    matches = [_h2h("Yankland", "Zedland", 1, 1)]
    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams,
        group_matches=matches,
        context="group_standings",
        fifa_rankings=["France", "Brazil"],  # neither tied team listed
    )
    assert [t["team"] for t in sorted_teams] == ["Yankland", "Zedland"]
    assert len(warnings) == 1


def test_step_2_descends_monotonically_does_not_restart() -> None:
    """Article 13 Step 2 progression d→e→f does not restart back at H2H.

    Scenario: 3 teams tied on points and on H2H (all three drew each
    other 1-1). Overall GD separates A (+5) from {B, C} (both 0).
    Overall GF: B=5, C=3 → B above C. The "does not restart" clause
    means that after step 2 d separates A, {B, C} continues at step 2 e
    (not back at step 1). Same answer here either way; this pins the
    progression so future changes can't introduce a back-edge.
    """
    teams = [
        _stand("A", "A", points=6, gd=+5, gf=7),
        _stand("B", "A", points=6, gd= 0, gf=5),
        _stand("C", "A", points=6, gd= 0, gf=3),
    ]
    matches = [
        _h2h("A", "B", 1, 1),
        _h2h("B", "C", 1, 1),
        _h2h("A", "C", 1, 1),
    ]
    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams,
        group_matches=matches,
        context="group_standings",
        fifa_rankings=[],
    )
    # A separates via step 2 d. B vs C separates via step 2 e. No fair-
    # play tier reached for either, so no warnings.
    assert [t["team"] for t in sorted_teams] == ["A", "B", "C"]
    assert warnings == []


def test_third_place_uses_fifa_rankings_after_overall_stats_tie() -> None:
    """Article 13 third-placed-teams chain has NO H2H step (different
    groups never met). Order is overall pts → overall GD → overall GF
    → fair-play (warn, skip) → FIFA Rankings → alphabetical.

    Non-coincidental: Zambia sorts alphabetically AFTER Brazil, so a
    "Zambia ranks above Brazil" result must come from FIFA Rankings.
    """
    teams = [
        _stand("Brazil", "C", points=3, gd=0, gf=2),
        _stand("Zambia", "B", points=3, gd=0, gf=2),
    ]
    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams,
        group_matches=None,  # cross-group → no H2H
        context="third_place_qualifying",
        fifa_rankings=["Zambia", "Brazil"],  # Zambia ranked above
    )
    assert [t["team"] for t in sorted_teams] == ["Zambia", "Brazil"]
    assert len(warnings) == 1
    assert warnings[0]["context"] == "third_place_qualifying"


def test_full_chain_resolves_four_way_zero_zero_group_via_fifa_rankings() -> None:
    """Real-world flavour test: a 4-team group where every match is 0-0.

    Non-coincidental: rankings deliberately disagree with alphabetical
    order so the final order proves FIFA Rankings drove the resolution.
    """
    teams = [
        _stand("Argentina", "A", points=3, gd=0, gf=0),
        _stand("Belgium",   "A", points=3, gd=0, gf=0),
        _stand("Croatia",   "A", points=3, gd=0, gf=0),
        _stand("Denmark",   "A", points=3, gd=0, gf=0),
    ]
    matches = [
        _h2h("Argentina", "Belgium", 0, 0),
        _h2h("Argentina", "Croatia", 0, 0),
        _h2h("Argentina", "Denmark", 0, 0),
        _h2h("Belgium",   "Croatia", 0, 0),
        _h2h("Belgium",   "Denmark", 0, 0),
        _h2h("Croatia",   "Denmark", 0, 0),
    ]
    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams,
        group_matches=matches,
        context="group_standings",
        # Reverse-alphabetical rankings prove the resolver consulted them.
        fifa_rankings=["Denmark", "Croatia", "Belgium", "Argentina"],
    )
    assert [t["team"] for t in sorted_teams] == [
        "Denmark", "Croatia", "Belgium", "Argentina",
    ]
    assert len(warnings) == 1
    assert warnings[0]["tied_teams"] == ["Argentina", "Belgium", "Croatia", "Denmark"]


def test_apply_fifa_tiebreakers_defaults_to_alphabetical_when_rankings_omitted() -> None:
    """When `fifa_rankings` is omitted, the helper treats it as empty and
    falls through to alphabetical — production callers should resolve
    rankings from the DB via `_resolve_fifa_rankings(session)` and pass
    them in explicitly."""
    teams = [
        _stand("Argentina", "A", points=6, gd=2, gf=4),
        _stand("Spain",     "A", points=6, gd=2, gf=4),
    ]
    matches = [_h2h("Argentina", "Spain", 1, 1)]
    sorted_teams, warnings = _apply_fifa_tiebreakers(
        teams,
        group_matches=matches,
        context="group_standings",
        # fifa_rankings omitted → empty → alphabetical
    )
    assert [t["team"] for t in sorted_teams] == ["Argentina", "Spain"]
    assert len(warnings) == 1


# ── Advancement-from-groups scoring (the +10 round_of_32 base) ──────────────
#
# Qualifying from a group IS reaching the round of 32, so get_actual_advancement
# must credit it the moment qualification is settled — NOT defer it until the
# eventual R32 knockout match is played. Before this was fixed, a correct top-2
# call scored only the +5/+5 position bonus (10) at group completion; the
# +10/+10 advancement base waited for the knockout stage. These tests lock the
# timing so the full 30 lands the instant the group completes — exactly when the
# whole pool reads the Phase 1 → Phase 2 leaderboard.

# Decisive results → SUI 9 (1st), CAN 6 (2nd), BOS 3 (3rd), QAT 0 (4th).
# Distinct points, so the ranking never touches a tiebreaker.
_GROUP_B_RESULTS = [
    ("Switzerland", "Qatar", 1, 0),
    ("Switzerland", "Bosnia-Herzegovina", 1, 0),
    ("Switzerland", "Canada", 1, 0),
    ("Canada", "Bosnia-Herzegovina", 1, 0),
    ("Canada", "Qatar", 1, 0),
    ("Bosnia-Herzegovina", "Qatar", 1, 0),
]


async def _seed_group_results(
    session: AsyncSession,
    competition_id: UUID,
    group: str,
    results: list[tuple[str, str, int, int]],
    *,
    status: MatchStatus = MatchStatus.FINISHED,
) -> list[Fixture]:
    """Seed a group's round-robin and return the committed fixtures (with ids)."""
    fixtures = [
        _add_match(
            session, competition_id,
            home=h, away=a, home_score=hs, away_score=as_,
            group=group, status=status,
        )
        for (h, a, hs, as_) in results
    ]
    await session.commit()
    for fx in fixtures:
        await session.refresh(fx)
    return fixtures


async def test_top_two_credited_round_of_32_when_their_group_completes(
    session: AsyncSession, competition: Competition
) -> None:
    """1st/2nd in a COMPLETED group reach round_of_32 immediately; 3rd is
    gated (best-8 thirds undecidable until all groups finish) and 4th never
    qualifies. No knockout fixture exists — qualification alone drives it."""
    await _seed_group_results(session, competition.id, "B", _GROUP_B_RESULTS)
    # A second, still-incomplete group keeps all_groups_complete False, so the
    # third-place gate stays shut.
    _add_match(
        session, competition.id,
        home="Mexico", away="South Korea", home_score=0, away_score=0,
        group="A", status=MatchStatus.SCHEDULED,
    )
    await session.commit()

    adv = await get_actual_advancement(session)

    assert adv.get("Switzerland") == "round_of_32"  # 1st
    assert adv.get("Canada") == "round_of_32"       # 2nd
    assert "Bosnia-Herzegovina" not in adv          # 3rd — gate shut
    assert "Qatar" not in adv                       # 4th — never
    assert "Mexico" not in adv and "South Korea" not in adv  # group incomplete


async def test_third_place_credited_only_once_all_groups_complete(
    session: AsyncSession, competition: Competition
) -> None:
    """When every group is complete, a best-8 third-placed team reaches
    round_of_32 too (here Group B is the only group, so its 3rd qualifies).
    4th still never does."""
    await _seed_group_results(session, competition.id, "B", _GROUP_B_RESULTS)

    adv = await get_actual_advancement(session)

    assert adv.get("Switzerland") == "round_of_32"
    assert adv.get("Canada") == "round_of_32"
    assert adv.get("Bosnia-Herzegovina") == "round_of_32"  # 3rd, gate open
    assert "Qatar" not in adv                              # 4th — never


async def test_correct_top_two_worth_full_30_before_any_knockout_match(
    session: AsyncSession, competition: Competition
) -> None:
    """The reported bug: a user who correctly calls both top-2 teams should
    see 30 bracket points (10 + 10 advancement base, 5 + 5 position bonus)
    the moment the group completes — not 10. Mirrors Luke Aarohi / Group B."""
    fixtures = await _seed_group_results(session, competition.id, "B", _GROUP_B_RESULTS)
    # Group A left incomplete: no knockout stage could have started.
    _add_match(
        session, competition.id,
        home="Mexico", away="South Korea", home_score=0, away_score=0,
        group="A", status=MatchStatus.SCHEDULED,
    )
    await session.commit()

    user = User(email="luke@example.com", name="Luke")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Predict every Group B score exactly → predicted table == actual table,
    # so Switzerland(1) and Canada(2) land in their real positions.
    for fx, (_h, _a, hs, as_) in zip(fixtures, _GROUP_B_RESULTS):
        session.add(MatchPrediction(
            user_id=user.id, fixture_id=fx.id,
            home_score=hs, away_score=as_, phase=PredictionPhase.PHASE_1,
        ))
    # Bracket picks: both top-2 teams into the round of 32.
    session.add(TeamPrediction(
        user_id=user.id, team="Switzerland", stage="round_of_32",
        phase=PredictionPhase.PHASE_1,
    ))
    session.add(TeamPrediction(
        user_id=user.id, team="Canada", stage="round_of_32",
        phase=PredictionPhase.PHASE_1,
    ))
    await session.commit()

    breakdown = await calculate_user_points(session, user.id)

    assert breakdown.phase1.round_of_32_points == 20     # 10 + 10 base
    assert breakdown.phase1.group_position_points == 10  # 5 + 5 position
    assert breakdown.bracket_total == 30

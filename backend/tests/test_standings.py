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
from app.models.score import Score, ScoreSource
from app.services.standings import (
    get_actual_group_standings,
    get_group_positions,
    get_qualifying_third_place_teams,
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


async def test_alphabetical_fallback_when_all_equal(session, competition) -> None:
    """Final-fallback tiebreaker is team-name alphabetical (NOT FIFA's actual rule).

    FIFA's full tiebreaker chain is: points → GD → goals-for → head-to-head
    points → head-to-head GD → head-to-head goals → fair-play points → drawing
    of lots. Our implementation skips head-to-head and fair-play and goes
    straight to alphabetical. For deterministic outcomes in a prediction app
    that's acceptable — but if FIFA resolves a real tie via head-to-head and
    we resolve via alphabetical, the predicted standings will disagree with
    the official table.

    This test pins the current (simplified) behaviour so anyone changing it
    has to do so explicitly.
    """
    # All four teams draw 0-0 with each other → identical stats.
    _add_match(session, competition.id, home="Argentina", away="Belgium", home_score=0, away_score=0)
    _add_match(session, competition.id, home="Argentina", away="Croatia", home_score=0, away_score=0)
    _add_match(session, competition.id, home="Argentina", away="Denmark", home_score=0, away_score=0)
    _add_match(session, competition.id, home="Belgium", away="Croatia", home_score=0, away_score=0)
    _add_match(session, competition.id, home="Belgium", away="Denmark", home_score=0, away_score=0)
    _add_match(session, competition.id, home="Croatia", away="Denmark", home_score=0, away_score=0)
    await session.commit()

    standings = await get_actual_group_standings(session)
    assert [t["team"] for t in standings["A"]] == ["Argentina", "Belgium", "Croatia", "Denmark"]


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

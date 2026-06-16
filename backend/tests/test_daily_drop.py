"""Daily Drop picks awards.

Each PICKS-page award shows ONE winner: when several tie, the least-featured-so-far
player gets it (alphabetical tiebreak) so awards spread across the group instead of
one person sweeping the page. The Hipster is whoever's picks were LEAST popular
across the day (lowest average outcome-agreement). ``_fmt_names`` still does the
overflow formatting for the (multi-name) table-page stats.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score, ScoreSource
from app.models.user import User
from app.services.daily_drop import (
    _fmt_names,
    _pick_stats,
    _position_tenure,
    _todays_match_returns,
)

SINCE = timedelta(hours=30)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _fixture(session, comp, home, away, hs, as_, *, group):
    fx = Fixture(
        competition_id=comp.id, home_team=home, away_team=away,
        kickoff=utc_now() - timedelta(hours=2), stage="group", group=group,
        status=MatchStatus.FINISHED,
    )
    session.add(fx)
    session.add(Score(fixture=fx, home_score=hs, away_score=as_, source=ScoreSource.API))
    await session.commit()
    await session.refresh(fx)
    return fx


async def _user(session, name, email):
    u = User(email=email, name=name)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _pred(session, user, fx, h, a):
    session.add(MatchPrediction(
        user_id=user.id, fixture_id=fx.id, home_score=h, away_score=a,
        phase=PredictionPhase.PHASE_1,
    ))
    await session.commit()


def test_fmt_names_overflow():
    assert _fmt_names([]) == "Nobody"
    assert _fmt_names(["A"]) == "A"
    assert _fmt_names(["A", "B"]) == "A & B"
    assert _fmt_names(["A", "B", "C"]) == "A, B & C"
    assert _fmt_names(["A", "B", "C", "D"]) == "A, B +2"
    assert _fmt_names(["A", "B", "C", "D", "E"]) == "A, B +3"


@pytest.mark.asyncio
async def test_picks_one_winner_spread_and_hipster(session):
    comp = Competition(name="WC", entry_fee=Decimal("0"), external_id="WC", is_active=True)
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    # One match, 2-0 home win. Alice & Bob both NAIL 2-0 (tied for Nostradamus);
    # Cara picks a draw and Dave an away win — both wrong, and each the lone voice
    # on their outcome → both 0% agreement (Hipster candidates).
    fx = await _fixture(session, comp, "Mexico", "South Africa", 2, 0, group="A")
    alice = await _user(session, "Alice", "alice@e.com")
    bob = await _user(session, "Bob", "bob@e.com")
    cara = await _user(session, "Cara", "cara@e.com")
    dave = await _user(session, "Dave", "dave@e.com")
    await _pred(session, alice, fx, 2, 0)
    await _pred(session, bob, fx, 2, 0)
    await _pred(session, cara, fx, 1, 1)
    await _pred(session, dave, fx, 0, 1)

    called, contrarian, blunder, n = await _pick_stats(
        session, since=utc_now() - SINCE, feature_count={}
    )
    assert n == 1
    # Single winner per award (NOT a tied list); called_it carries the tied count.
    assert called is not None and called.names == ["Alice"] and called.count == 2
    # Biggest wrong-outcome swing is Dave's 0-1 (gd −1 vs +2 → 3) over Cara's draw (2).
    assert blunder is not None and blunder.names == ["Dave"] and blunder.predicted == "0-1"
    # Cara & Dave tie at 0% agreement, but Dave already holds the blunder, so the
    # least-featured tiebreak spreads the Hipster to Cara.
    assert contrarian is not None and contrarian.names == ["Cara"] and contrarian.avg_pct == 0


@pytest.mark.asyncio
async def test_blunder_lists_only_the_identical_worst_pick(session):
    comp = Competition(name="WC", entry_fee=Decimal("0"), external_id="WC", is_active=True)
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    fx = await _fixture(session, comp, "Germany", "Curacao", 7, 1, group="B")
    anna = await _user(session, "Anna", "anna@e.com")
    bob = await _user(session, "Bob", "bob@e.com")
    cara = await _user(session, "Cara", "cara@e.com")
    # Anna & Bob make the IDENTICAL worst pick (0-3, swing 9); Cara is also wrong
    # (1-2, swing 7) but a different pick — she must NOT be grouped in.
    await _pred(session, anna, fx, 0, 3)
    await _pred(session, bob, fx, 0, 3)
    await _pred(session, cara, fx, 1, 2)

    _called, _contra, blunder, _n = await _pick_stats(
        session, since=utc_now() - SINCE, feature_count={}
    )
    assert blunder is not None
    assert blunder.predicted == "0-3"
    # Single winner: least-featured of the tied identical-pick makers {Anna, Bob}.
    assert blunder.names == ["Anna"]  # not Bob, and not Cara (different pick)


@pytest.mark.asyncio
async def test_todays_returns_excludes_out_of_window_matches(session):
    """Today's Returns must reflect ONLY matches in the drop window — the bug it
    replaced summed season-to-date category totals. An exact hit OUTSIDE the
    window must not contribute; a hit INSIDE must."""
    comp = Competition(name="WC", entry_fee=Decimal("0"), external_id="WC", is_active=True)
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    # In-window match (kickoff −2h, via _fixture). Out-of-window match (−40h, well
    # past the 30h window) added by hand.
    fx_now = await _fixture(session, comp, "Mexico", "South Africa", 2, 0, group="A")
    fx_old = Fixture(
        competition_id=comp.id, home_team="Brazil", away_team="Serbia",
        kickoff=utc_now() - timedelta(hours=40), stage="group", group="B",
        status=MatchStatus.FINISHED,
    )
    session.add(fx_old)
    session.add(Score(fixture=fx_old, home_score=3, away_score=1, source=ScoreSource.API))
    await session.commit()
    await session.refresh(fx_old)

    # Alice: WRONG in-window (0 pts), EXACT out-of-window (would inflate a
    # cumulative breakdown) → today's returns must be EMPTY.
    alice = await _user(session, "Alice", "alice@e.com")
    await _pred(session, alice, fx_now, 0, 2)
    await _pred(session, alice, fx_old, 3, 1)
    # Bob: EXACT in-window → returns are non-empty and include the exact bonus.
    bob = await _user(session, "Bob", "bob@e.com")
    await _pred(session, bob, fx_now, 2, 0)

    since = utc_now() - SINCE
    alice_cats = await _todays_match_returns(session, alice.id, since=since)
    bob_cats = await _todays_match_returns(session, bob.id, since=since)

    assert alice_cats == []  # the out-of-window exact hit is excluded
    labels = {c.label for c in bob_cats}
    assert "Exact scores" in labels and "Correct outcomes" in labels
    assert sum(c.points for c in bob_cats) > 0


@pytest.mark.asyncio
async def test_position_tenure_counts_consecutive_days(session):
    """_position_tenure counts consecutive recent snapshot days the same leader /
    last has held the spot, stopping at the first day that differs."""
    alice = await _user(session, "Alice", "alice@e.com")
    bob = await _user(session, "Bob", "bob@e.com")
    dave = await _user(session, "Dave", "dave@e.com")
    today = utc_now().date()

    # 3 days. Alice tops all three. Dave is last on the two most recent days; on
    # the oldest day Bob was last instead → Dave's spoon tenure stops at 2.
    plan = [
        (today - timedelta(days=2), {alice.id: 1, dave.id: 2, bob.id: 3}),
        (today - timedelta(days=1), {alice.id: 1, bob.id: 2, dave.id: 3}),
        (today, {alice.id: 1, bob.id: 2, dave.id: 3}),
    ]
    for d, positions in plan:
        for uid, pos in positions.items():
            session.add(LeaderboardSnapshot(
                user_id=uid, position=pos, total_points=0, captured_date=d,
            ))
    await session.commit()

    leader_days, spoon_days = await _position_tenure(session, {alice.id}, {dave.id})
    assert leader_days == 3
    assert spoon_days == 2

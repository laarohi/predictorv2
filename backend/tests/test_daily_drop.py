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
    _clueless_stat,
    _daily_points,
    _fmt_names,
    _pick_stats,
    _position_tenure,
    _todays_match_results,
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
        session, since=utc_now() - SINCE, until=utc_now(), feature_count={}
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
        session, since=utc_now() - SINCE, until=utc_now(), feature_count={}
    )
    assert blunder is not None
    assert blunder.predicted == "0-3"
    # Single winner: least-featured of the tied identical-pick makers {Anna, Bob}.
    assert blunder.names == ["Anna"]  # not Bob, and not Cara (different pick)


@pytest.mark.asyncio
async def test_todays_match_results_window_bounds_and_flags(session):
    """The Your Day recap must cover ONLY the matches in the drop window
    (kickoff in [since, until]) — anchored to the drop, not the viewer's clock —
    and classify each as exact / outcome / miss. A 0-point miss is INCLUDED (the
    bug it replaced hid the day entirely when nothing was banked)."""
    comp = Competition(name="WC", entry_fee=Decimal("0"), external_id="WC", is_active=True)
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    # Recent match (kickoff −2h, via _fixture) and an older one (−40h).
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

    alice = await _user(session, "Alice", "alice@e.com")
    await _pred(session, alice, fx_now, 0, 2)  # WRONG outcome → miss, 0 pts
    await _pred(session, alice, fx_old, 3, 1)  # EXACT

    now = utc_now()
    # Window ending now → only the recent match; the −40h one is before `since`.
    recent = await _todays_match_results(session, alice.id, since=now - SINCE, until=now)
    assert len(recent) == 1
    assert recent[0].home_team == "Mexico"
    assert recent[0].result == "miss" and recent[0].points == 0  # a miss is shown
    assert recent[0].predicted == "0-2" and recent[0].actual == "2-0"

    # Window [−50h, −20h] → only the older match (the recent one is after `until`).
    older = await _todays_match_results(
        session, alice.id, since=now - timedelta(hours=50), until=now - timedelta(hours=20)
    )
    assert len(older) == 1
    assert older[0].home_team == "Brazil"
    assert older[0].result == "exact" and older[0].points > 0


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


@pytest.mark.asyncio
async def test_daily_points_window_and_ghost_exclusion(session):
    """_daily_points sums each REAL player's match points over [since, until] only.
    A player who predicted an in-window match but scored nothing is a key with 0
    (so Clueless can find them); a player's exact on an OUT-of-window match adds
    nothing; ghosts never appear. This is the multi-user 'Your Day' — it shares the
    same scoring, so Big Earner / Clueless / Your Day can't disagree."""
    comp = Competition(name="WC", entry_fee=Decimal("0"), external_id="WC", is_active=True)
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    fx_in1 = await _fixture(session, comp, "Spain", "Japan", 2, 1, group="A")   # in window
    fx_in2 = await _fixture(session, comp, "Italy", "Ghana", 1, 0, group="A")   # in window
    fx_out = Fixture(
        competition_id=comp.id, home_team="Peru", away_team="Qatar",
        kickoff=utc_now() - timedelta(hours=50), stage="group", group="C",
        status=MatchStatus.FINISHED,
    )
    session.add(fx_out)
    session.add(Score(fixture=fx_out, home_score=3, away_score=3, source=ScoreSource.API))
    await session.commit()
    await session.refresh(fx_out)

    alice = await _user(session, "Alice", "alice@e.com")  # nails fx_in1 exactly
    bob = await _user(session, "Bob", "bob@e.com")         # misses in-window, exact OUT of window
    ghost = User(email="crowd@e.com", name="The Crowd", is_ghost=True)
    session.add(ghost)
    await session.commit()
    await session.refresh(ghost)

    await _pred(session, alice, fx_in1, 2, 1)  # EXACT → points
    await _pred(session, alice, fx_in2, 0, 2)  # wrong outcome → 0
    await _pred(session, bob, fx_in1, 0, 0)    # wrong → 0
    await _pred(session, bob, fx_out, 3, 3)    # exact but OUT of window → ignored
    await _pred(session, ghost, fx_in1, 2, 1)  # ghost exact → excluded entirely

    now = utc_now()
    totals = await _daily_points(
        session, since=now - SINCE, until=now, ghost_ids={ghost.id}
    )

    assert totals.get(alice.id, 0) > 0           # banked on the exact
    assert bob.id in totals and totals[bob.id] == 0  # played in window, scored zero
    assert ghost.id not in totals                # ghosts excluded


def test_clueless_lists_all_when_few():
    """A small tied set names everyone; tied_count == len(names); not a floor."""
    import uuid as _uuid
    from datetime import datetime, timezone

    ref = datetime(2026, 6, 17, 8, 30, tzinfo=timezone.utc)
    ids = [_uuid.uuid4() for _ in range(4)]
    names = {ids[0]: "Ann", ids[1]: "Bob", ids[2]: "Cy", ids[3]: "Dee"}
    daily = {ids[0]: 1, ids[1]: 1, ids[2]: 5, ids[3]: 9}  # Ann & Bob tied worst on 1
    fc: dict[str, int] = {}

    c = _clueless_stat(daily, names, reference=ref, feature_count=fc)
    assert c is not None
    assert c.names == ["Ann", "Bob"]
    assert c.tied_count == 2 and c.points == 1 and c.is_floor is False
    assert fc["Ann"] == 1 and fc["Bob"] == 1  # both recorded as featured


def test_clueless_collapses_big_zero_floor():
    """A big tie (mass zero-point day) collapses to ONE representative + the true
    tied_count, flagged as a floor. The pick is deterministic for a given drop."""
    import uuid as _uuid
    from datetime import datetime, timezone

    ref = datetime(2026, 6, 17, 8, 30, tzinfo=timezone.utc)
    floor = [_uuid.uuid4() for _ in range(6)]
    winner = _uuid.uuid4()
    names = {u: f"P{i}" for i, u in enumerate(floor)}
    names[winner] = "TopDog"
    daily = {u: 0 for u in floor}
    daily[winner] = 5

    c = _clueless_stat(daily, names, reference=ref, feature_count={})
    assert c is not None
    assert len(c.names) == 1 and c.names[0] in [names[u] for u in floor]
    assert c.tied_count == 6 and c.points == 0 and c.is_floor is True
    # Same drop → same scapegoat (rotation is deterministic per date).
    again = _clueless_stat(daily, names, reference=ref, feature_count={})
    assert again.names == c.names


def test_clueless_suppressed_when_no_dunce():
    """No Clueless when everyone is level on a real score, or with <2 players."""
    import uuid as _uuid
    from datetime import datetime, timezone

    ref = datetime(2026, 6, 17, 8, 30, tzinfo=timezone.utc)
    a, b = _uuid.uuid4(), _uuid.uuid4()
    names = {a: "Ann", b: "Bob"}
    assert _clueless_stat({a: 5, b: 5}, names, reference=ref, feature_count={}) is None
    assert _clueless_stat({a: 0}, names, reference=ref, feature_count={}) is None

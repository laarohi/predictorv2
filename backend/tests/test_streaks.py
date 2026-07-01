"""Hot/cold form streaks for the leaderboard chip.

``get_user_streaks()`` returns the TRAILING run of finished matches ending at
the most recent result: hot = consecutive correct outcomes, cold = consecutive
misses, ordered by kickoff. Exactly one is ever non-zero. Correctness is
outcome-level (1/X/2), NOT exact score — exact-score streaks would read 0–1 and
never trigger the chip.
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
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score, ScoreSource
from app.models.user import User
from app.services.leaderboard import get_user_streaks

BASE_KICKOFF = utc_now().replace(
    hour=12, minute=0, second=0, microsecond=0
) - timedelta(days=10)

# Outcome shorthands. Actual result is always a home win (2-0 → '1'); the
# prediction's outcome decides hit vs miss.
WIN = (2, 0)   # actual: home win → outcome '1'
HIT = (1, 0)   # predicts a home win → correct outcome
MISS = (0, 1)  # predicts an away win → wrong outcome


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _user_and_comp(session: AsyncSession) -> tuple[User, Competition]:
    comp = Competition(
        name="WC2026", entry_fee=Decimal("0"), external_id="WC", is_active=True
    )
    user = User(email="alice@example.com", name="Alice")
    session.add_all([comp, user])
    await session.commit()
    await session.refresh(comp)
    await session.refresh(user)
    return user, comp


async def _add_match(
    session: AsyncSession,
    comp: Competition,
    user: User,
    actual: tuple[int, int],
    predicted: tuple[int, int],
    *,
    hours: float,
) -> None:
    """One finished fixture (kickoff = BASE + ``hours``) + the user's prediction.

    ``hours`` sets the kickoff offset explicitly so chronological ordering is
    independent of insertion order — the streak walks by kickoff.
    """
    fx = Fixture(
        competition_id=comp.id,
        home_team="A",
        away_team="B",
        kickoff=BASE_KICKOFF + timedelta(hours=hours),
        stage="group",
        group="A",
        status=MatchStatus.FINISHED,
    )
    session.add(fx)
    session.add(
        Score(fixture=fx, home_score=actual[0], away_score=actual[1], source=ScoreSource.API)
    )
    await session.commit()
    await session.refresh(fx)
    session.add(
        MatchPrediction(
            user_id=user.id,
            fixture_id=fx.id,
            home_score=predicted[0],
            away_score=predicted[1],
            phase=PredictionPhase.PHASE_1,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_no_finished_predictions_is_zero(session):
    user, _comp = await _user_and_comp(session)
    assert await get_user_streaks(session, user.id) == (0, 0)


@pytest.mark.asyncio
async def test_hot_streak_counts_trailing_correct_run(session):
    user, comp = await _user_and_comp(session)
    # An early miss, then the latest three correct → hot 3, cold 0.
    await _add_match(session, comp, user, WIN, MISS, hours=0)
    await _add_match(session, comp, user, WIN, HIT, hours=1)
    await _add_match(session, comp, user, WIN, HIT, hours=2)
    await _add_match(session, comp, user, WIN, HIT, hours=3)
    assert await get_user_streaks(session, user.id) == (3, 0)


@pytest.mark.asyncio
async def test_cold_streak_counts_trailing_miss_run(session):
    user, comp = await _user_and_comp(session)
    await _add_match(session, comp, user, WIN, HIT, hours=0)
    await _add_match(session, comp, user, WIN, MISS, hours=1)
    await _add_match(session, comp, user, WIN, MISS, hours=2)
    assert await get_user_streaks(session, user.id) == (0, 2)


@pytest.mark.asyncio
async def test_only_the_trailing_run_counts(session):
    user, comp = await _user_and_comp(session)
    # A long hot run broken by a single miss at the end → cold 1, hot 0.
    await _add_match(session, comp, user, WIN, HIT, hours=0)
    await _add_match(session, comp, user, WIN, HIT, hours=1)
    await _add_match(session, comp, user, WIN, HIT, hours=2)
    await _add_match(session, comp, user, WIN, MISS, hours=3)
    assert await get_user_streaks(session, user.id) == (0, 1)


@pytest.mark.asyncio
async def test_ordering_is_by_kickoff_not_insertion(session):
    user, comp = await _user_and_comp(session)
    # Insert out of chronological order. The latest KICKOFF (hours=9) is a miss,
    # so the trailing run is cold 1 — even though it was inserted second.
    await _add_match(session, comp, user, WIN, HIT, hours=5)
    await _add_match(session, comp, user, WIN, MISS, hours=9)  # latest by kickoff
    await _add_match(session, comp, user, WIN, HIT, hours=1)
    assert await get_user_streaks(session, user.id) == (0, 1)


@pytest.mark.asyncio
async def test_draw_outcome_counts_as_hit(session):
    user, comp = await _user_and_comp(session)
    # Actual draws ('X'); both predictions are also draws → hits, regardless of
    # the exact scoreline. Confirms streaks are outcome-level, not exact-score.
    await _add_match(session, comp, user, (1, 1), (0, 0), hours=0)
    await _add_match(session, comp, user, (2, 2), (3, 3), hours=1)
    assert await get_user_streaks(session, user.id) == (2, 0)


@pytest.mark.asyncio
async def test_streak_hit_miss_uses_regulation_not_et_or_pens(session):
    """A knockout match decided in extra time grades hit/miss on the 90-minute
    result, matching calculate_user_points — not the ET/penalty winner."""
    user, comp = await _user_and_comp(session)
    await _add_match(session, comp, user, WIN, HIT, hours=0)
    await _add_match(session, comp, user, WIN, HIT, hours=1)

    # Finished 1-1 after 90 min, 2-1 after extra time. The user predicts the
    # regulation draw: a HIT under 90-minute grading, a MISS if graded on the
    # ET "1" (home win) result — this is the regression the fix guards against.
    fx = Fixture(
        competition_id=comp.id, home_team="Brazil", away_team="Croatia",
        kickoff=BASE_KICKOFF + timedelta(hours=2), stage="quarter_final",
        status=MatchStatus.FINISHED,
    )
    session.add(fx)
    session.add(Score(
        fixture=fx, home_score=1, away_score=1,
        home_score_et=2, away_score_et=1, source=ScoreSource.API,
    ))
    await session.commit()
    await session.refresh(fx)
    session.add(MatchPrediction(
        user_id=user.id, fixture_id=fx.id, home_score=1, away_score=1,
        phase=PredictionPhase.PHASE_2,
    ))
    await session.commit()

    assert await get_user_streaks(session, user.id) == (3, 0)

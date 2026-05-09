"""Tests for the windowing logic in score_sync.has_active_or_imminent_match."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.services.score_sync import has_active_or_imminent_match


@pytest_asyncio.fixture
async def session() -> AsyncSession:
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


def _fixture(competition_id, *, kickoff: datetime, status: MatchStatus, ext: str) -> Fixture:
    return Fixture(
        competition_id=competition_id,
        external_id=ext,
        home_team="Mexico",
        away_team="South Africa",
        kickoff=kickoff,
        stage="group",
        group="A",
        status=status,
    )


NOW = datetime(2026, 6, 11, 19, 0)


@pytest.mark.asyncio
async def test_returns_false_when_db_empty(session, competition) -> None:
    assert await has_active_or_imminent_match(session, now=NOW) is False


@pytest.mark.asyncio
async def test_returns_true_when_match_is_live(session, competition) -> None:
    session.add(_fixture(competition.id, kickoff=NOW - timedelta(hours=1), status=MatchStatus.LIVE, ext="1"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is True


@pytest.mark.asyncio
async def test_returns_true_when_match_is_at_halftime(session, competition) -> None:
    session.add(_fixture(competition.id, kickoff=NOW - timedelta(minutes=45), status=MatchStatus.HALFTIME, ext="2"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is True


@pytest.mark.asyncio
async def test_returns_true_for_imminent_kickoff_within_buffer(session, competition) -> None:
    # Kickoff in 9 minutes — within the 10-minute pre-kickoff buffer
    session.add(_fixture(competition.id, kickoff=NOW + timedelta(minutes=9), status=MatchStatus.SCHEDULED, ext="3"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is True


@pytest.mark.asyncio
async def test_returns_false_when_kickoff_is_far_away(session, competition) -> None:
    # Kickoff in 2 hours — outside the buffer
    session.add(_fixture(competition.id, kickoff=NOW + timedelta(hours=2), status=MatchStatus.SCHEDULED, ext="4"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is False


@pytest.mark.asyncio
async def test_returns_true_for_potentially_overrunning_match(session, competition) -> None:
    # Status still SCHEDULED but kickoff was 2 hours ago — could be a match
    # whose status didn't update from a missed poll. Buffer says yes-poll.
    session.add(_fixture(competition.id, kickoff=NOW - timedelta(hours=2), status=MatchStatus.SCHEDULED, ext="5"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is True


@pytest.mark.asyncio
async def test_returns_false_when_match_finished_long_ago(session, competition) -> None:
    session.add(_fixture(competition.id, kickoff=NOW - timedelta(days=1), status=MatchStatus.FINISHED, ext="6"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is False

"""Tests for the admin score-update endpoint (manual result entry)."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from app.api.scores import update_score
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource
from app.schemas.score import ScoreUpdate


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def fixture_row(session: AsyncSession) -> Fixture:
    comp = Competition(name="WC2026", entry_fee=Decimal("0"), external_id="WC")
    session.add(comp)
    await session.commit()
    fx = Fixture(
        competition_id=comp.id,
        home_team="Mexico",
        away_team="South Africa",
        kickoff=datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc),
        stage="group",
        group="A",
        status=MatchStatus.LIVE,
    )
    session.add(fx)
    await session.commit()
    await session.refresh(fx)
    return fx


@pytest.mark.asyncio
async def test_manual_score_defaults_to_finished(session, fixture_row) -> None:
    payload = ScoreUpdate(home_score=2, away_score=1, verified=True)
    read = await update_score(fixture_row.id, payload, session, MagicMock())

    assert read.source == ScoreSource.MANUAL
    assert read.verified is True
    await session.refresh(fixture_row)
    assert fixture_row.status == MatchStatus.FINISHED


@pytest.mark.asyncio
async def test_manual_score_can_keep_match_live(session, fixture_row) -> None:
    # Mid-match correction while the external feed is down: score lands,
    # but the fixture must NOT be marked finished.
    payload = ScoreUpdate(home_score=1, away_score=0, status=MatchStatus.LIVE)
    await update_score(fixture_row.id, payload, session, MagicMock())

    await session.refresh(fixture_row)
    assert fixture_row.status == MatchStatus.LIVE
    q = await session.execute(select(Score).where(Score.fixture_id == fixture_row.id))
    score = q.scalar_one()
    assert (score.home_score, score.away_score) == (1, 0)


@pytest.mark.asyncio
async def test_manual_score_overwrites_api_score(session, fixture_row) -> None:
    session.add(
        Score(fixture_id=fixture_row.id, home_score=0, away_score=0, source=ScoreSource.API)
    )
    await session.commit()

    payload = ScoreUpdate(home_score=3, away_score=2, verified=True)
    read = await update_score(fixture_row.id, payload, session, MagicMock())

    assert (read.home_score, read.away_score) == (3, 2)
    assert read.source == ScoreSource.MANUAL

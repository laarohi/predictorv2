"""DB-level uniqueness on prediction tables (sec-authz:AUTH-2).

The models previously declared a no-op `Config.unique_together`; these tests
pin the real UniqueConstraints now enforced via __table_args__ (and the
matching migration d9e3b7a1c4f2).
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.mark.asyncio
async def test_duplicate_match_prediction_rejected(session):
    uid, fid = uuid.uuid4(), uuid.uuid4()
    session.add(MatchPrediction(user_id=uid, fixture_id=fid, home_score=1, away_score=0))
    await session.commit()

    session.add(MatchPrediction(user_id=uid, fixture_id=fid, home_score=2, away_score=2))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_team_prediction_unique_allows_different_phase():
    # Same (user, team, stage) is allowed across phases — phase is in the key.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        uid = uuid.uuid4()
        session.add(
            TeamPrediction(user_id=uid, team="Brazil", stage="winner", phase=PredictionPhase.PHASE_1)
        )
        session.add(
            TeamPrediction(user_id=uid, team="Brazil", stage="winner", phase=PredictionPhase.PHASE_2)
        )
        await session.commit()  # different phase → fine

        session.add(
            TeamPrediction(user_id=uid, team="Brazil", stage="winner", phase=PredictionPhase.PHASE_1)
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

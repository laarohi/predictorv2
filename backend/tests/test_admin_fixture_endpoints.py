"""Regression tests for the admin fixture-override endpoints.

create_fixture / update_fixture / update_fixture_status previously did
``return fixture_to_read(fixture)`` — calling the async helper without await,
without its required session, and without the phase1_locked arg — so every
call raised. These tests invoke the handlers end-to-end against an in-memory
DB to lock in the fix (await + session + phase1_locked, score eager-loaded).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from app.api.fixtures import (
    create_fixture,
    update_fixture,
    update_fixture_status,
)
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.schemas.fixture import FixtureCreate, FixtureStatusUpdate, FixtureUpdate

KICKOFF = datetime(2026, 6, 28, 19, 0, tzinfo=timezone.utc)


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


async def test_create_fixture_returns_read(session, competition) -> None:
    data = FixtureCreate(
        competition_id=competition.id,
        home_team="France",
        away_team="Germany",
        kickoff=KICKOFF,
        stage="round_of_32",
        group=None,
        match_number=73,
        external_id="537417",
    )
    read = await create_fixture(data, session, _admin=None)
    assert read.home_team == "France"
    assert read.away_team == "Germany"
    assert read.match_number == 73
    assert read.score is None  # freshly created, no Score → no lazy-load crash

    # Persisted.
    rows = (await session.execute(select(Fixture))).scalars().all()
    assert len(rows) == 1


async def test_update_fixture_returns_read(session, competition) -> None:
    fx = Fixture(
        competition_id=competition.id,
        home_team="A1",
        away_team="B2",
        kickoff=KICKOFF,
        stage="round_of_32",
        external_id="537417",
        status=MatchStatus.SCHEDULED,
    )
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    read = await update_fixture(
        fx.id,
        FixtureUpdate(home_team="Brazil", away_team="Spain"),
        session,
        _admin=None,
    )
    assert read.home_team == "Brazil"
    assert read.away_team == "Spain"


async def test_update_fixture_status_returns_read(session, competition) -> None:
    fx = Fixture(
        competition_id=competition.id,
        home_team="A1",
        away_team="B2",
        kickoff=KICKOFF,
        stage="round_of_32",
        external_id="537417",
        status=MatchStatus.SCHEDULED,
    )
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    read = await update_fixture_status(
        fx.id,
        FixtureStatusUpdate(status=MatchStatus.LIVE, minute=10),
        session,
        _admin=None,
    )
    assert read.status == MatchStatus.LIVE
    assert read.minute == 10

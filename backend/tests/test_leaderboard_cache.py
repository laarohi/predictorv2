"""Leaderboard caching: single-flight rebuild + admin-only force refresh.

Covers performance findings PERF-2 (cache stampede / public force-refresh) and
the auth gate on ?refresh=true. The single-flight test relies on the lock
serializing DB access: with the lock, N concurrent cold-miss calls share one
session safely and coalesce into a single rebuild (one last_calculated);
without it they would interleave on the shared session.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.api import leaderboard as lb_api
from app.services.leaderboard import calculate_leaderboard, invalidate_cache


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.mark.asyncio
async def test_second_call_within_ttl_is_cache_hit(session):
    invalidate_cache()
    r1 = await calculate_leaderboard(session, phase=None)
    r2 = await calculate_leaderboard(session, phase=None)
    # A cache hit returns the same stored timestamp (no recompute).
    assert r1.last_calculated == r2.last_calculated


@pytest.mark.asyncio
async def test_concurrent_cold_misses_coalesce_to_one_rebuild(session):
    invalidate_cache()
    results = await asyncio.gather(
        *[calculate_leaderboard(session, phase=None) for _ in range(8)]
    )
    stamps = {r.last_calculated for r in results}
    # Single-flight: exactly one rebuild; the other 7 were served the cache.
    assert len(stamps) == 1


@pytest.mark.asyncio
async def test_force_refresh_ignored_for_non_admin():
    captured = {}

    async def fake_calc(session, force_refresh=False, phase=None):
        captured["force"] = force_refresh
        return MagicMock()

    non_admin = MagicMock()
    non_admin.is_admin = False
    with patch.object(lb_api, "calculate_leaderboard", new=fake_calc):
        await lb_api.get_leaderboard(
            session=MagicMock(), _user=non_admin, refresh=True, phase=None
        )
    assert captured["force"] is False


@pytest.mark.asyncio
async def test_force_refresh_honored_for_admin():
    captured = {}

    async def fake_calc(session, force_refresh=False, phase=None):
        captured["force"] = force_refresh
        return MagicMock()

    admin = MagicMock()
    admin.is_admin = True
    with patch.object(lb_api, "calculate_leaderboard", new=fake_calc):
        await lb_api.get_leaderboard(
            session=MagicMock(), _user=admin, refresh=True, phase=None
        )
    assert captured["force"] is True


@pytest.mark.asyncio
async def test_force_refresh_ignored_for_anonymous():
    captured = {}

    async def fake_calc(session, force_refresh=False, phase=None):
        captured["force"] = force_refresh
        return MagicMock()

    with patch.object(lb_api, "calculate_leaderboard", new=fake_calc):
        await lb_api.get_leaderboard(
            session=MagicMock(), _user=None, refresh=True, phase=None
        )
    assert captured["force"] is False

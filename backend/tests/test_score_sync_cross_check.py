"""Settlement cross-check (score_sync._apply_external_score + _cross_check_final).

Every match that finalizes off ESPN's scoreboard running total (groups,
regulation-decided knockouts) is validated, exactly once at the LIVE->FINISHED
transition, against the provider's independent authoritative final (the summary
linescores). A disagreement is logged (not overridden) for an admin to verify —
the catch-all that makes EVERY settled match summary-validated, not just the
ET/penalty knockouts the live path overlays.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.services.external_scores import ExternalScore
from app.services.score_sync import ScoreSyncResult, _apply_external_score


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


class _FakeProvider:
    """Stands in for the score provider's independent check."""

    def __init__(self, check):
        self._check = check
        self.calls = 0

    async def fetch_final_check(self, ext):
        self.calls += 1
        return self._check


async def _make_fixture(session, competition, *, status, stage="group"):
    fx = Fixture(
        competition_id=competition.id,
        external_id="fd-1",
        home_team="Spain",
        away_team="Austria",
        kickoff=datetime(2026, 6, 25, 19, 0, tzinfo=timezone.utc),
        stage=stage,
        group="A" if stage == "group" else None,
        status=status,
    )
    session.add(fx)
    await session.commit()
    await session.refresh(fx)
    return fx


def _finished_ext(**kw):
    base = dict(
        external_id="", home_team="Spain", away_team="Austria",
        home_score=2, away_score=1, status=MatchStatus.FINISHED,
        period=2, final_authoritative=False, espn_event_id="ev1",
    )
    base.update(kw)
    return ExternalScore(**base)


@pytest.mark.asyncio
async def test_matching_final_logs_no_warning(session, competition, caplog):
    fx = await _make_fixture(session, competition, status=MatchStatus.SCHEDULED)
    provider = _FakeProvider((2, 1, None, None))  # agrees with the 2-1 stored final
    res = ScoreSyncResult()

    with caplog.at_level(logging.WARNING, logger="app.services.score_sync"):
        await _apply_external_score(session, competition.id, _finished_ext(), res, provider=provider)

    assert provider.calls == 1
    assert "MISMATCH" not in caplog.text


@pytest.mark.asyncio
async def test_disagreeing_final_logs_mismatch(session, competition, caplog):
    fx = await _make_fixture(session, competition, status=MatchStatus.SCHEDULED)
    provider = _FakeProvider((3, 1, None, None))  # summary says 3-1, we stored 2-1
    res = ScoreSyncResult()

    with caplog.at_level(logging.WARNING, logger="app.services.score_sync"):
        await _apply_external_score(session, competition.id, _finished_ext(), res, provider=provider)

    assert provider.calls == 1
    assert "SETTLEMENT MISMATCH" in caplog.text
    assert "(2, 1, None, None)" in caplog.text  # stored
    assert "(3, 1, None, None)" in caplog.text  # summary


@pytest.mark.asyncio
async def test_no_check_when_already_finished(session, competition, caplog):
    # Re-applying to an already-FINISHED fixture is not a settlement transition.
    fx = await _make_fixture(session, competition, status=MatchStatus.FINISHED)
    provider = _FakeProvider((9, 9, None, None))  # would mismatch if it ran
    res = ScoreSyncResult()

    with caplog.at_level(logging.WARNING, logger="app.services.score_sync"):
        await _apply_external_score(session, competition.id, _finished_ext(), res, provider=provider)

    assert provider.calls == 0
    assert "MISMATCH" not in caplog.text


@pytest.mark.asyncio
async def test_no_check_when_already_authoritative(session, competition, caplog):
    # ET/penalty knockouts are overlaid from the summary already — don't
    # re-fetch to cross-check them.
    fx = await _make_fixture(session, competition, status=MatchStatus.SCHEDULED, stage="round_of_32")
    provider = _FakeProvider((9, 9, None, None))
    res = ScoreSyncResult()
    ext = _finished_ext(home_score_et=2, away_score_et=1, final_authoritative=True)

    with caplog.at_level(logging.WARNING, logger="app.services.score_sync"):
        await _apply_external_score(session, competition.id, ext, res, provider=provider)

    assert provider.calls == 0


@pytest.mark.asyncio
async def test_no_provider_no_check(session, competition, caplog):
    # Back-compat: callers that don't pass a provider get no cross-check.
    fx = await _make_fixture(session, competition, status=MatchStatus.SCHEDULED)
    res = ScoreSyncResult()

    with caplog.at_level(logging.WARNING, logger="app.services.score_sync"):
        await _apply_external_score(session, competition.id, _finished_ext(), res)

    assert "MISMATCH" not in caplog.text

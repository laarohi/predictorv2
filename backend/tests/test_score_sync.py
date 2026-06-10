"""Tests for score_sync: windowing logic + the sync/resolution passes."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score
from app.services.external_scores import ExternalScore
from app.services.score_sync import has_active_or_imminent_match, sync_scores_once


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


NOW = datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)


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


# ---------------------------------------------------------------------------
# sync_scores_once: live apply + the per-fixture resolution pass
# ---------------------------------------------------------------------------


class FakeProvider:
    """Score provider double: a canned live response + per-id lookups."""

    def __init__(self, live: list[ExternalScore], by_id: dict[str, ExternalScore] | None = None):
        self.live = live
        self.by_id = by_id or {}
        self.fixture_fetches: list[str] = []

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        return self.live

    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        self.fixture_fetches.append(str(fixture_id))
        return self.by_id.get(str(fixture_id))


def _ext(ext_id: str, status: MatchStatus, home: int = 0, away: int = 0) -> ExternalScore:
    return ExternalScore(
        external_id=ext_id,
        home_team="Mexico",
        away_team="South Africa",
        home_score=home,
        away_score=away,
        status=status,
    )


async def _get_score(session: AsyncSession, fixture_id) -> Score | None:
    q = await session.execute(select(Score).where(Score.fixture_id == fixture_id))
    return q.scalar_one_or_none()


@pytest.mark.asyncio
async def test_live_fixture_absent_from_response_is_resolved_to_finished(
    session, competition, monkeypatch
) -> None:
    # DB says LIVE, but the live-filtered response no longer contains the
    # match — Football-Data marked it FINISHED. The resolution pass must
    # fetch it individually and land the final score + status.
    fx = _fixture(competition.id, kickoff=NOW - timedelta(hours=2), status=MatchStatus.LIVE, ext="100")
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    provider = FakeProvider(live=[], by_id={"100": _ext("100", MatchStatus.FINISHED, 2, 1)})
    monkeypatch.setattr("app.services.score_sync.get_score_provider", lambda: provider)

    result = await sync_scores_once(session)

    assert provider.fixture_fetches == ["100"]
    assert result.synced == 1 and not result.errors
    await session.refresh(fx)
    assert fx.status == MatchStatus.FINISHED
    score = await _get_score(session, fx.id)
    assert score is not None and (score.home_score, score.away_score) == (2, 1)


@pytest.mark.asyncio
async def test_scheduled_fixture_past_kickoff_is_resolved(
    session, competition, monkeypatch
) -> None:
    # Backend was down through the whole match: status never left SCHEDULED.
    # The resolution pass picks it up from the recent-kickoff window. Unlike
    # the LIVE-status cases, this window is evaluated against the real clock
    # inside sync_scores_once, so the kickoff must be relative to utc_now().
    fx = _fixture(competition.id, kickoff=utc_now() - timedelta(hours=3), status=MatchStatus.SCHEDULED, ext="101")
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    provider = FakeProvider(live=[], by_id={"101": _ext("101", MatchStatus.FINISHED, 0, 3)})
    monkeypatch.setattr("app.services.score_sync.get_score_provider", lambda: provider)

    await sync_scores_once(session)

    await session.refresh(fx)
    assert fx.status == MatchStatus.FINISHED
    score = await _get_score(session, fx.id)
    assert score is not None and (score.home_score, score.away_score) == (0, 3)


@pytest.mark.asyncio
async def test_resolution_does_not_fabricate_score_for_unstarted_match(
    session, competition, monkeypatch
) -> None:
    # Delayed kickoff: our DB thinks the match should have started, but the
    # API still reports TIMED (→ SCHEDULED). Status syncs back, yet no 0-0
    # Score row may be written for a match that hasn't been played.
    fx = _fixture(competition.id, kickoff=NOW - timedelta(minutes=30), status=MatchStatus.LIVE, ext="102")
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    provider = FakeProvider(live=[], by_id={"102": _ext("102", MatchStatus.SCHEDULED)})
    monkeypatch.setattr("app.services.score_sync.get_score_provider", lambda: provider)

    result = await sync_scores_once(session)

    assert result.synced == 0 and result.updated == 0
    await session.refresh(fx)
    assert fx.status == MatchStatus.SCHEDULED
    assert await _get_score(session, fx.id) is None


@pytest.mark.asyncio
async def test_espn_style_score_without_external_id_matches_by_name(
    session, competition, monkeypatch
) -> None:
    # The ESPN provider carries no Football-Data external_id — the fixture
    # must match via team names, and once touched it must NOT be re-fetched
    # by the resolution pass (which would let a laggier source overwrite
    # the fresh live score on the same tick).
    fx = _fixture(competition.id, kickoff=NOW - timedelta(minutes=30), status=MatchStatus.LIVE, ext="104")
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    live = ExternalScore(
        external_id="",
        home_team="Mexico",
        away_team="South Africa",
        home_score=2,
        away_score=1,
        status=MatchStatus.LIVE,
        minute=67,
    )
    provider = FakeProvider(live=[live])
    monkeypatch.setattr("app.services.score_sync.get_score_provider", lambda: provider)

    result = await sync_scores_once(session)

    assert provider.fixture_fetches == []  # touched by name-match → no resolve call
    assert result.synced == 1
    await session.refresh(fx)
    assert fx.status == MatchStatus.LIVE and fx.minute == 67
    score = await _get_score(session, fx.id)
    assert score is not None and (score.home_score, score.away_score) == (2, 1)


@pytest.mark.asyncio
async def test_fixture_present_in_live_response_is_not_fetched_individually(
    session, competition, monkeypatch
) -> None:
    # Normal in-play tick: bulk response covers the match, so the resolution
    # pass must not spend an extra API call on it.
    fx = _fixture(competition.id, kickoff=NOW - timedelta(minutes=30), status=MatchStatus.LIVE, ext="103")
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    provider = FakeProvider(live=[_ext("103", MatchStatus.LIVE, 1, 0)])
    monkeypatch.setattr("app.services.score_sync.get_score_provider", lambda: provider)

    result = await sync_scores_once(session)

    assert provider.fixture_fetches == []
    assert result.synced == 1
    await session.refresh(fx)
    assert fx.status == MatchStatus.LIVE
    score = await _get_score(session, fx.id)
    assert score is not None and (score.home_score, score.away_score) == (1, 0)

"""Tests for fixture_sync — mapping helpers, upsert, sync entry points."""

from datetime import datetime

import pytest

from app.models.fixture import MatchStatus
from app.services.fixture_sync import (
    FixtureRecord,
    UnknownGroupError,
    UnknownStageError,
    _map_group,
    _map_stage,
    _record_from_match,
)


# Sample resolved group-stage match (matches probe response shape)
RESOLVED_MATCH = {
    "id": 537327,
    "utcDate": "2026-06-11T19:00:00Z",
    "status": "TIMED",
    "matchday": 1,
    "stage": "GROUP_STAGE",
    "group": "GROUP_A",
    "lastUpdated": "2025-12-06T20:20:44Z",
    "homeTeam": {"id": 769, "name": "Mexico", "shortName": "Mexico", "tla": "MEX"},
    "awayTeam": {"id": 774, "name": "South Africa", "shortName": "South Africa", "tla": "RSA"},
}

# Sample knockout match with null teams
NULL_TEAM_MATCH = {
    "id": 537417,
    "utcDate": "2026-06-28T19:00:00Z",
    "status": "TIMED",
    "matchday": None,
    "stage": "LAST_32",
    "group": None,
    "homeTeam": {"id": None, "name": None, "shortName": None, "tla": None},
    "awayTeam": {"id": None, "name": None, "shortName": None, "tla": None},
}


class TestMapStage:
    @pytest.mark.parametrize(
        "api_stage, expected",
        [
            ("GROUP_STAGE", "group"),
            ("LAST_32", "round_of_32"),
            ("LAST_16", "round_of_16"),
            ("QUARTER_FINALS", "quarter_final"),
            ("SEMI_FINALS", "semi_final"),
            ("THIRD_PLACE", "third_place"),
            ("FINAL", "final"),
        ],
    )
    def test_known_stages(self, api_stage: str, expected: str) -> None:
        assert _map_stage(api_stage) == expected

    def test_unknown_raises(self) -> None:
        with pytest.raises(UnknownStageError, match="GALACTIC_FINAL"):
            _map_stage("GALACTIC_FINAL")


class TestMapGroup:
    def test_strips_prefix(self) -> None:
        assert _map_group("GROUP_A") == "A"
        assert _map_group("GROUP_L") == "L"

    def test_none_returns_none(self) -> None:
        assert _map_group(None) is None

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(UnknownGroupError, match="POOL_A"):
            _map_group("POOL_A")


class TestRecordFromMatch:
    def test_resolved_teams(self) -> None:
        rec = _record_from_match(RESOLVED_MATCH)
        assert rec.external_id == "537327"
        assert rec.home_team == "Mexico"
        assert rec.away_team == "South Africa"
        # Naive UTC, matching the Fixture.kickoff schema convention
        assert rec.kickoff == datetime(2026, 6, 11, 19, 0)
        assert rec.kickoff.tzinfo is None
        assert rec.stage == "group"
        assert rec.group == "A"
        assert rec.status == MatchStatus.SCHEDULED

    def test_null_teams_synthesises_slot_strings(self) -> None:
        rec = _record_from_match(NULL_TEAM_MATCH)
        assert rec.external_id == "537417"
        assert rec.home_team == "slot:round_of_32:537417:home"
        assert rec.away_team == "slot:round_of_32:537417:away"
        assert rec.stage == "round_of_32"
        assert rec.group is None


# ----- Upsert tests -----

from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.competition import Competition
from app.services.fixture_sync import SyncResult, _upsert_fixtures


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """In-memory SQLite session for fast unit tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(session: AsyncSession) -> Competition:
    comp = Competition(name="FIFA World Cup 2026", entry_fee=Decimal("0"))
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


def _record(
    *,
    ext: str,
    home: str = "Mexico",
    away: str = "South Africa",
    kickoff: datetime = datetime(2026, 6, 11, 19, 0),
    stage: str = "group",
    group: str | None = "A",
) -> FixtureRecord:
    return FixtureRecord(
        external_id=ext,
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        stage=stage,
        group=group,
        status=MatchStatus.SCHEDULED,
    )


class TestUpsertFixtures:
    @pytest.mark.asyncio
    async def test_inserts_new_fixtures(self, session, competition) -> None:
        records = [_record(ext="1"), _record(ext="2", home="Brazil", away="Croatia")]
        result = await _upsert_fixtures(session, records, competition.id)
        assert result.created == 2
        assert result.updated == 0
        assert result.unchanged == 0

    @pytest.mark.asyncio
    async def test_skips_unchanged(self, session, competition) -> None:
        records = [_record(ext="1")]
        await _upsert_fixtures(session, records, competition.id)
        result2 = await _upsert_fixtures(session, records, competition.id)
        assert result2.created == 0
        assert result2.updated == 0
        assert result2.unchanged == 1

    @pytest.mark.asyncio
    async def test_updates_kickoff_change(self, session, competition) -> None:
        await _upsert_fixtures(session, [_record(ext="1")], competition.id)
        changed = [_record(ext="1", kickoff=datetime(2026, 6, 11, 20, 0))]
        result = await _upsert_fixtures(session, changed, competition.id)
        assert result.updated == 1
        assert result.changed_fields["kickoff"] == 1

    @pytest.mark.asyncio
    async def test_updates_team_resolution(self, session, competition) -> None:
        # Simulate a knockout slot getting a real team
        await _upsert_fixtures(
            session,
            [
                _record(
                    ext="1",
                    home="slot:round_of_32:1:home",
                    away="slot:round_of_32:1:away",
                    stage="round_of_32",
                    group=None,
                )
            ],
            competition.id,
        )
        resolved = [_record(ext="1", home="USA", away="Spain", stage="round_of_32", group=None)]
        result = await _upsert_fixtures(session, resolved, competition.id)
        assert result.updated == 1
        assert result.changed_fields["home_team"] == 1
        assert result.changed_fields["away_team"] == 1

    @pytest.mark.asyncio
    async def test_db_only_logged_not_deleted(self, session, competition) -> None:
        # Insert one, then sync with a different external_id — original stays
        await _upsert_fixtures(session, [_record(ext="1")], competition.id)
        result = await _upsert_fixtures(session, [_record(ext="2")], competition.id)
        assert result.created == 1
        assert result.db_only_count == 1


# ----- sync_from_cache tests -----

from pathlib import Path

from app.services.fixture_sync import sync_from_cache


SAMPLE_PATH = Path(__file__).parent / "fixtures" / "wc2026_sample.json"


class TestSyncFromCache:
    @pytest.mark.asyncio
    async def test_reads_json_and_upserts(self, session, competition) -> None:
        result = await sync_from_cache(session, competition.id, SAMPLE_PATH)
        assert result.created == 8
        assert result.updated == 0
        # Re-run from same file → all unchanged
        result2 = await sync_from_cache(session, competition.id, SAMPLE_PATH)
        assert result2.created == 0
        assert result2.unchanged == 8

    @pytest.mark.asyncio
    async def test_missing_file_raises(self, session, competition) -> None:
        with pytest.raises(FileNotFoundError):
            await sync_from_cache(session, competition.id, Path("/no/such/file.json"))

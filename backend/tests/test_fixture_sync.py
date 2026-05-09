"""Tests for fixture_sync — mapping helpers, upsert, sync entry points."""

from datetime import datetime, timezone

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
        assert rec.kickoff == datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)
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

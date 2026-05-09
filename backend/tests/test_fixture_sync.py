"""Tests for fixture_sync — mapping helpers, upsert, sync entry points."""

import pytest

from app.services.fixture_sync import (
    UnknownGroupError,
    UnknownStageError,
    _map_group,
    _map_stage,
)


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

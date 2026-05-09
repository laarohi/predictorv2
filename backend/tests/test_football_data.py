"""Tests for the Football-Data shared client (logic only, no HTTP)."""

import pytest

from app.models.fixture import MatchStatus
from app.services.external.football_data import map_status


@pytest.mark.parametrize(
    "api_status, expected",
    [
        ("SCHEDULED", MatchStatus.SCHEDULED),
        ("TIMED", MatchStatus.SCHEDULED),
        ("IN_PLAY", MatchStatus.LIVE),
        ("EXTRA_TIME", MatchStatus.LIVE),
        ("PENALTY_SHOOTOUT", MatchStatus.LIVE),
        ("PAUSED", MatchStatus.HALFTIME),
        ("FINISHED", MatchStatus.FINISHED),
        ("AWARDED", MatchStatus.FINISHED),
        ("POSTPONED", MatchStatus.POSTPONED),
        ("SUSPENDED", MatchStatus.POSTPONED),
        ("CANCELLED", MatchStatus.CANCELLED),
    ],
)
def test_map_status_known_codes(api_status: str, expected: MatchStatus) -> None:
    assert map_status(api_status) == expected


def test_map_status_unknown_falls_back_to_scheduled() -> None:
    assert map_status("WAT_IS_THIS") == MatchStatus.SCHEDULED

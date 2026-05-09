"""Shared Football-Data.org HTTP client.

Used by both fixture_sync (for seeding) and external_scores (for live scoring).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import get_settings
from app.models.fixture import MatchStatus


class FootballDataError(Exception):
    """Catch-all for Football-Data.org HTTP / parsing failures."""


class FootballDataAuthError(FootballDataError):
    """401 / 403 from Football-Data — bad or missing token."""


class FootballDataRateLimitError(FootballDataError):
    """429 from Football-Data after retry."""


_STATUS_MAP = {
    "SCHEDULED": MatchStatus.SCHEDULED,
    "TIMED": MatchStatus.SCHEDULED,
    "IN_PLAY": MatchStatus.LIVE,
    "EXTRA_TIME": MatchStatus.LIVE,
    "PENALTY_SHOOTOUT": MatchStatus.LIVE,
    "PAUSED": MatchStatus.HALFTIME,
    "FINISHED": MatchStatus.FINISHED,
    "AWARDED": MatchStatus.FINISHED,
    "POSTPONED": MatchStatus.POSTPONED,
    "SUSPENDED": MatchStatus.POSTPONED,
    "CANCELLED": MatchStatus.CANCELLED,
}


def map_status(api_status: str) -> MatchStatus:
    """Map a Football-Data status enum to our MatchStatus.

    Unknown values fall back to SCHEDULED with no warning — callers can
    log if they need stricter behaviour.
    """
    return _STATUS_MAP.get(api_status, MatchStatus.SCHEDULED)

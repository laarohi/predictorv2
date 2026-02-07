"""External score fetching service.

Fetches live scores from external APIs (API-Football, Football-Data.org).
Supports multiple providers with automatic fallback.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import httpx

from app.models.fixture import MatchStatus


class ScoreProvider(str, Enum):
    """Supported external score providers."""

    API_FOOTBALL = "api_football"
    FOOTBALL_DATA = "football_data"


@dataclass
class ExternalScore:
    """Score data from external API."""

    external_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    status: MatchStatus
    minute: int | None = None
    # Extra time / penalties
    home_score_et: int | None = None
    away_score_et: int | None = None
    home_penalties: int | None = None
    away_penalties: int | None = None


class ScoreProviderBase(ABC):
    """Base class for score providers."""

    @abstractmethod
    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        """Fetch live scores for a competition."""
        ...

    @abstractmethod
    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        """Fetch score for a specific fixture."""
        ...


class APIFootballProvider(ScoreProviderBase):
    """API-Football.com provider.

    Requires API_FOOTBALL_KEY environment variable.
    Free tier: 100 requests/day.
    """

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self) -> None:
        self.api_key = os.getenv("API_FOOTBALL_KEY", "")
        self.headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "v3.football.api-sports.io",
        }

    def _map_status(self, status: str) -> MatchStatus:
        """Map API-Football status to our MatchStatus."""
        status_map = {
            "TBD": MatchStatus.SCHEDULED,
            "NS": MatchStatus.SCHEDULED,
            "1H": MatchStatus.LIVE,
            "HT": MatchStatus.HALFTIME,
            "2H": MatchStatus.LIVE,
            "ET": MatchStatus.LIVE,
            "P": MatchStatus.LIVE,
            "FT": MatchStatus.FINISHED,
            "AET": MatchStatus.FINISHED,
            "PEN": MatchStatus.FINISHED,
            "PST": MatchStatus.POSTPONED,
            "CANC": MatchStatus.CANCELLED,
            "ABD": MatchStatus.CANCELLED,
        }
        return status_map.get(status, MatchStatus.SCHEDULED)

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        """Fetch live scores from API-Football."""
        if not self.api_key:
            return []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/fixtures",
                headers=self.headers,
                params={"league": competition_id, "live": "all"},
                timeout=10.0,
            )

            if response.status_code != 200:
                return []

            data = response.json()
            scores = []

            for fixture in data.get("response", []):
                teams = fixture.get("teams", {})
                goals = fixture.get("goals", {})
                status_info = fixture.get("fixture", {}).get("status", {})
                score_info = fixture.get("score", {})

                external_score = ExternalScore(
                    external_id=str(fixture.get("fixture", {}).get("id", "")),
                    home_team=teams.get("home", {}).get("name", ""),
                    away_team=teams.get("away", {}).get("name", ""),
                    home_score=goals.get("home") or 0,
                    away_score=goals.get("away") or 0,
                    status=self._map_status(status_info.get("short", "")),
                    minute=status_info.get("elapsed"),
                    home_score_et=score_info.get("extratime", {}).get("home"),
                    away_score_et=score_info.get("extratime", {}).get("away"),
                    home_penalties=score_info.get("penalty", {}).get("home"),
                    away_penalties=score_info.get("penalty", {}).get("away"),
                )
                scores.append(external_score)

            return scores

    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        """Fetch score for a specific fixture."""
        if not self.api_key:
            return None

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/fixtures",
                headers=self.headers,
                params={"id": fixture_id},
                timeout=10.0,
            )

            if response.status_code != 200:
                return None

            data = response.json()
            fixtures = data.get("response", [])

            if not fixtures:
                return None

            fixture = fixtures[0]
            teams = fixture.get("teams", {})
            goals = fixture.get("goals", {})
            status_info = fixture.get("fixture", {}).get("status", {})
            score_info = fixture.get("score", {})

            return ExternalScore(
                external_id=str(fixture.get("fixture", {}).get("id", "")),
                home_team=teams.get("home", {}).get("name", ""),
                away_team=teams.get("away", {}).get("name", ""),
                home_score=goals.get("home") or 0,
                away_score=goals.get("away") or 0,
                status=self._map_status(status_info.get("short", "")),
                minute=status_info.get("elapsed"),
                home_score_et=score_info.get("extratime", {}).get("home"),
                away_score_et=score_info.get("extratime", {}).get("away"),
                home_penalties=score_info.get("penalty", {}).get("home"),
                away_penalties=score_info.get("penalty", {}).get("away"),
            )


class FootballDataProvider(ScoreProviderBase):
    """Football-Data.org provider.

    Requires FOOTBALL_DATA_KEY environment variable.
    Free tier: 10 requests/minute.
    """

    BASE_URL = "https://api.football-data.org/v4"

    def __init__(self) -> None:
        self.api_key = os.getenv("FOOTBALL_DATA_KEY", "")
        self.headers = {"X-Auth-Token": self.api_key}

    def _map_status(self, status: str) -> MatchStatus:
        """Map Football-Data status to our MatchStatus."""
        status_map = {
            "SCHEDULED": MatchStatus.SCHEDULED,
            "TIMED": MatchStatus.SCHEDULED,
            "IN_PLAY": MatchStatus.LIVE,
            "PAUSED": MatchStatus.HALFTIME,
            "FINISHED": MatchStatus.FINISHED,
            "POSTPONED": MatchStatus.POSTPONED,
            "CANCELLED": MatchStatus.CANCELLED,
            "SUSPENDED": MatchStatus.CANCELLED,
        }
        return status_map.get(status, MatchStatus.SCHEDULED)

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        """Fetch live scores from Football-Data.org."""
        if not self.api_key:
            return []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/competitions/{competition_id}/matches",
                headers=self.headers,
                params={"status": "LIVE,IN_PLAY,PAUSED"},
                timeout=10.0,
            )

            if response.status_code != 200:
                return []

            data = response.json()
            scores = []

            for match in data.get("matches", []):
                score_info = match.get("score", {})
                full_time = score_info.get("fullTime", {})

                external_score = ExternalScore(
                    external_id=str(match.get("id", "")),
                    home_team=match.get("homeTeam", {}).get("name", ""),
                    away_team=match.get("awayTeam", {}).get("name", ""),
                    home_score=full_time.get("home") or 0,
                    away_score=full_time.get("away") or 0,
                    status=self._map_status(match.get("status", "")),
                    minute=match.get("minute"),
                )
                scores.append(external_score)

            return scores

    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        """Fetch score for a specific fixture."""
        if not self.api_key:
            return None

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/matches/{fixture_id}",
                headers=self.headers,
                timeout=10.0,
            )

            if response.status_code != 200:
                return None

            match = response.json()
            score_info = match.get("score", {})
            full_time = score_info.get("fullTime", {})

            return ExternalScore(
                external_id=str(match.get("id", "")),
                home_team=match.get("homeTeam", {}).get("name", ""),
                away_team=match.get("awayTeam", {}).get("name", ""),
                home_score=full_time.get("home") or 0,
                away_score=full_time.get("away") or 0,
                status=self._map_status(match.get("status", "")),
                minute=match.get("minute"),
            )


# Provider registry
PROVIDERS: dict[ScoreProvider, type[ScoreProviderBase]] = {
    ScoreProvider.API_FOOTBALL: APIFootballProvider,
    ScoreProvider.FOOTBALL_DATA: FootballDataProvider,
}


def get_score_provider(provider: ScoreProvider | None = None) -> ScoreProviderBase:
    """Get the configured score provider.

    Args:
        provider: Specific provider to use. If None, auto-detects based on available API keys.

    Returns:
        Score provider instance.
    """
    if provider:
        return PROVIDERS[provider]()

    # Auto-detect based on available keys
    if os.getenv("API_FOOTBALL_KEY"):
        return APIFootballProvider()
    if os.getenv("FOOTBALL_DATA_KEY"):
        return FootballDataProvider()

    # Return API-Football as default (even without key, will return empty results)
    return APIFootballProvider()

"""Fixture sync — Football-Data API → DB Fixture rows.

Pure business logic. Imports the shared HTTP client; does NOT import
Settings directly. Caller passes session and competition_id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.fixture import MatchStatus
from app.services.external.football_data import map_status


class FixtureSyncError(Exception):
    """Catch-all for fixture_sync failures."""


class UnknownStageError(FixtureSyncError):
    """API returned a `stage` value we don't recognise."""


class UnknownGroupError(FixtureSyncError):
    """API returned a `group` value we don't recognise."""


_STAGE_MAP = {
    "GROUP_STAGE": "group",
    "LAST_32": "round_of_32",
    "LAST_16": "round_of_16",
    "QUARTER_FINALS": "quarter_final",
    "SEMI_FINALS": "semi_final",
    "THIRD_PLACE": "third_place",
    "FINAL": "final",
}


def _map_stage(api_stage: str) -> str:
    """Map Football-Data `stage` enum to our Fixture.stage string."""
    try:
        return _STAGE_MAP[api_stage]
    except KeyError as exc:
        raise UnknownStageError(f"Unknown Football-Data stage: {api_stage!r}") from exc


def _map_group(api_group: str | None) -> str | None:
    """Map Football-Data `group` enum (e.g. 'GROUP_A') to our group letter ('A')."""
    if api_group is None:
        return None
    if not api_group.startswith("GROUP_"):
        raise UnknownGroupError(f"Unknown Football-Data group format: {api_group!r}")
    return api_group.removeprefix("GROUP_")


@dataclass(frozen=True)
class FixtureRecord:
    """Normalised fixture record produced from a Football-Data match dict."""

    external_id: str
    home_team: str
    away_team: str
    kickoff: datetime
    stage: str
    group: str | None
    status: MatchStatus

    def to_kwargs(self, *, competition_id) -> dict[str, Any]:
        """Convert to keyword args for `Fixture(...)`."""
        return {
            "competition_id": competition_id,
            "external_id": self.external_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "kickoff": self.kickoff,
            "stage": self.stage,
            "group": self.group,
            "status": self.status,
        }


def _team_name_or_slot(team_dict: dict[str, Any], stage: str, external_id: str, side: str) -> str:
    """Return `team_dict["name"]` if non-null, else a synthesised slot string."""
    name = team_dict.get("name")
    if name:
        return name
    return f"slot:{stage}:{external_id}:{side}"


def _record_from_match(match: dict[str, Any]) -> FixtureRecord:
    """Map one Football-Data match dict to a FixtureRecord."""
    external_id = str(match["id"])
    stage = _map_stage(match["stage"])
    home = _team_name_or_slot(match.get("homeTeam") or {}, stage, external_id, "home")
    away = _team_name_or_slot(match.get("awayTeam") or {}, stage, external_id, "away")
    kickoff = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
    return FixtureRecord(
        external_id=external_id,
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        stage=stage,
        group=_map_group(match.get("group")),
        status=map_status(match.get("status", "")),
    )

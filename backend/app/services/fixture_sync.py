"""Fixture sync — Football-Data API → DB Fixture rows.

Pure business logic. Imports the shared HTTP client; does NOT import
Settings directly. Caller passes session and competition_id.
"""

from __future__ import annotations


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

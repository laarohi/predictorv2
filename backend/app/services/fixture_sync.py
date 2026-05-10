"""Fixture sync — Football-Data API → DB Fixture rows.

Pure business logic. Imports the shared HTTP client; does NOT import
Settings directly. Caller passes session and competition_id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.models._datetime import aware_utc
from app.models.fixture import MatchStatus
from app.services.external.football_data import map_status


def _parse_utc_kickoff(utc_iso: str) -> datetime:
    """Parse a Football-Data utcDate (e.g. '2026-06-11T19:00:00Z') to tz-aware UTC.

    Returns an aware datetime in UTC. Fixture.kickoff is now a TIMESTAMPTZ
    column; aware-vs-aware comparisons in `_upsert_fixtures` work directly.
    """
    aware = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    return aware.astimezone(timezone.utc)


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
    kickoff = _parse_utc_kickoff(match["utcDate"])
    return FixtureRecord(
        external_id=external_id,
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        stage=stage,
        group=_map_group(match.get("group")),
        status=map_status(match.get("status", "")),
    )


# ----- Upsert -----

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture


_DIFF_FIELDS = ("home_team", "away_team", "kickoff", "stage", "group", "status")


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    db_only_count: int = 0
    changed_fields: dict[str, int] = None  # type: ignore[assignment]
    unmatched_flag_teams: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.changed_fields is None:
            self.changed_fields = {}
        if self.unmatched_flag_teams is None:
            self.unmatched_flag_teams = []


async def _upsert_fixtures(
    session: AsyncSession,
    records: Iterable[FixtureRecord],
    competition_id: UUID,
) -> SyncResult:
    """Insert / update fixtures by external_id. Never deletes."""
    records = list(records)
    result_q = await session.execute(
        select(Fixture).where(Fixture.competition_id == competition_id)
    )
    existing = {f.external_id: f for f in result_q.scalars().all()}

    out = SyncResult()
    seen_ext_ids: set[str] = set()

    for rec in records:
        seen_ext_ids.add(rec.external_id)
        current = existing.get(rec.external_id)
        if current is None:
            session.add(Fixture(**rec.to_kwargs(competition_id=competition_id)))
            out.created += 1
            continue

        changed_here: list[str] = []
        for field in _DIFF_FIELDS:
            new_val = getattr(rec, field)
            old_val = getattr(current, field)
            # kickoff is tz-aware UTC; some DB drivers (aiosqlite) drop tzinfo on
            # read, so coerce both sides to aware UTC before comparing.
            if field == "kickoff":
                if aware_utc(new_val) != aware_utc(old_val):
                    setattr(current, field, new_val)
                    changed_here.append(field)
            elif new_val != old_val:
                setattr(current, field, new_val)
                changed_here.append(field)

        if changed_here:
            out.updated += 1
            for field in changed_here:
                out.changed_fields[field] = out.changed_fields.get(field, 0) + 1
        else:
            out.unchanged += 1

    out.db_only_count = len(set(existing.keys()) - seen_ext_ids)
    await session.commit()
    return out


# ----- Public sync entry points -----

import json
from pathlib import Path


async def sync_from_cache(
    session: AsyncSession,
    competition_id: UUID,
    cache_path: Path,
) -> SyncResult:
    """Read a Football-Data /matches response from disk and upsert."""
    if not cache_path.exists():
        raise FileNotFoundError(f"Cache file not found: {cache_path}")

    payload = json.loads(cache_path.read_text())
    matches = payload.get("matches", [])
    records = [_record_from_match(m) for m in matches]
    return await _upsert_fixtures(session, records, competition_id)


from app.services.external.football_data import FootballDataClient


class FootballDataEmptyResponseError(FixtureSyncError):
    """Football-Data returned zero matches — likely wrong competition code."""


async def sync_from_api(
    session: AsyncSession,
    competition_id: UUID,
    *,
    competition_code: str = "WC",
    cache_path: Path | None = None,
) -> SyncResult:
    """Fetch matches from Football-Data, optionally write to cache, then upsert."""
    client = FootballDataClient()
    matches = await client.get_matches(competition_code)

    if not matches:
        raise FootballDataEmptyResponseError(
            f"Football-Data returned zero matches for competition {competition_code!r}"
        )

    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"matches": matches}, indent=2))

    records = [_record_from_match(m) for m in matches]
    result = await _upsert_fixtures(session, records, competition_id)
    result.unmatched_flag_teams = _collect_unmatched_flag_teams(matches)
    return result


def _collect_unmatched_flag_teams(matches: list[dict]) -> list[str]:
    """Extract unique team names from matches and report any not present in flags.ts.

    Reads frontend/src/lib/utils/flags.ts as plain text and grep-matches keys.
    Best-effort — failing to read flags.ts logs a warning but doesn't fail the sync.
    """
    names: set[str] = set()
    for m in matches:
        for side in ("homeTeam", "awayTeam"):
            t = m.get(side) or {}
            n = t.get("name")
            if n:
                names.add(n)

    flags_path = Path(__file__).parents[3] / "frontend" / "src" / "lib" / "utils" / "flags.ts"
    try:
        flags_text = flags_path.read_text()
    except OSError:
        return []  # frontend file not accessible from this environment

    return sorted([n for n in names if f"'{n}'" not in flags_text and f'"{n}"' not in flags_text])

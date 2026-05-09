# WC2026 Fixtures Seeding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seed all 104 real WC2026 fixtures into the database from Football-Data.org, replacing the current placeholder data, while consolidating the existing live-scoring HTTP code onto a shared client.

**Architecture:** Five phased steps. Phase 1 introduces a shared `FootballDataClient` (HTTP, auth, errors). Phase 2 builds `fixture_sync` (the API-to-Fixture mapper) and the CLI script on top of it. Phase 3 refactors the existing `external_scores.py` to use the same shared client and deletes the dead-end `APIFootballProvider`. Phase 4 runs the seed against a freshly cleaned DB. Phase 5 commits the cache snapshot and tidies up unused config.

**Tech Stack:** Python 3.11, FastAPI, SQLModel + async SQLAlchemy, httpx, pytest + pytest-asyncio, Pydantic Settings. Tests run inside the backend container via `docker-compose exec backend python -m pytest`.

**Spec:** [`docs/superpowers/specs/2026-05-02-fixtures-seed-design.md`](../specs/2026-05-02-fixtures-seed-design.md)

---

## Phase 1 — Shared Football-Data client

### Task 1: Skeleton and `map_status` (TDD)

**Files:**
- Create: `backend/app/services/external/__init__.py`
- Create: `backend/app/services/external/football_data.py`
- Create: `backend/tests/test_football_data.py`

- [ ] **Step 1: Create empty package marker**

```bash
touch backend/app/services/external/__init__.py
```

- [ ] **Step 2: Write the failing tests for `map_status`**

Create `backend/tests/test_football_data.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
docker-compose exec -T backend python -m pytest tests/test_football_data.py -v
```

Expected: `ImportError: cannot import name 'map_status' from 'app.services.external.football_data'`

- [ ] **Step 4: Implement domain exceptions and `map_status`**

Create `backend/app/services/external/football_data.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker-compose exec -T backend python -m pytest tests/test_football_data.py -v
```

Expected: `12 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/external/__init__.py backend/app/services/external/football_data.py backend/tests/test_football_data.py
git commit -m "Add Football-Data shared client skeleton with status mapping"
```

---

### Task 2: `FootballDataClient` HTTP methods

**Files:**
- Modify: `backend/app/services/external/football_data.py`

**Note:** Per the spec, no unit tests for HTTP methods — they're integration-tested by the seed run in Phase 4. We commit a working client and verify by hitting a live endpoint manually.

- [ ] **Step 1: Add the `FootballDataClient` class**

Append to `backend/app/services/external/football_data.py`:

```python
class FootballDataClient:
    """Async HTTP wrapper for football-data.org/v4.

    Tournament-agnostic: caller provides competition codes (e.g. "WC").
    Reads token + base URL from app.config.Settings.
    """

    DEFAULT_TIMEOUT = 15.0
    MAX_RETRIES = 3
    BACKOFF_SECONDS = (1.0, 4.0, 9.0)

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        settings = get_settings()
        self._token = settings.football_data_token
        self._base = settings.football_data_base_url.rstrip("/")
        self._timeout = timeout
        self._headers = {"X-Auth-Token": self._token}

    async def get_competition(self, code: str) -> dict[str, Any]:
        """GET /v4/competitions/{code} — returns competition metadata."""
        return await self._request("GET", f"/competitions/{code}")

    async def get_matches(
        self,
        code: str,
        *,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /v4/competitions/{code}/matches — returns the list of matches.

        If status is provided (e.g. "LIVE,IN_PLAY,PAUSED"), filters server-side.
        """
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        payload = await self._request("GET", f"/competitions/{code}/matches", params=params)
        return list(payload.get("matches", []))

    async def get_match(self, match_id: str | int) -> dict[str, Any] | None:
        """GET /v4/matches/{id} — returns one match, or None on 404."""
        try:
            return await self._request("GET", f"/matches/{match_id}")
        except FootballDataError as exc:
            # Translate "not found" into None for caller convenience
            if "404" in str(exc):
                return None
            raise

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self._token:
            raise FootballDataAuthError("FOOTBALL_DATA_TOKEN is not set")

        url = f"{self._base}{path}"
        last_exc: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.request(method, url, headers=self._headers, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.BACKOFF_SECONDS[attempt])
                    continue
                raise FootballDataError(f"Network error after {self.MAX_RETRIES} attempts: {exc}") from exc

            if resp.status_code in (401, 403):
                raise FootballDataAuthError(f"HTTP {resp.status_code}: bad or missing FOOTBALL_DATA_TOKEN")

            if resp.status_code == 429:
                if attempt < self.MAX_RETRIES - 1:
                    reset = resp.headers.get("X-RequestCounter-Reset", "60")
                    try:
                        wait = float(reset)
                    except ValueError:
                        wait = 60.0
                    await asyncio.sleep(wait)
                    continue
                raise FootballDataRateLimitError("Rate limit exceeded after retry")

            if resp.status_code == 404:
                raise FootballDataError(f"HTTP 404 for {path}")

            if resp.status_code >= 400:
                raise FootballDataError(f"HTTP {resp.status_code} for {path}: {resp.text[:200]}")

            return resp.json()

        # Unreachable — every branch above either returns or raises
        raise FootballDataError(f"Exhausted retries for {path}; last error: {last_exc}")
```

- [ ] **Step 2: Verify import surface still works (no behaviour change)**

```bash
docker-compose exec -T backend python -c "from app.services.external.football_data import FootballDataClient, map_status, FootballDataError, FootballDataAuthError, FootballDataRateLimitError; print('imports OK')"
```

Expected: `imports OK`

- [ ] **Step 3: Smoke-test against the live API**

```bash
docker-compose run --rm backend python -c "
import asyncio
from app.services.external.football_data import FootballDataClient

async def main():
    c = FootballDataClient()
    info = await c.get_competition('WC')
    print(f'name={info[\"name\"]!r} season_id={info[\"currentSeason\"][\"id\"]}')
    matches = await c.get_matches('WC')
    print(f'matches={len(matches)}')

asyncio.run(main())
"
```

Expected output:
```
name='FIFA World Cup' season_id=2398
matches=104
```

- [ ] **Step 4: Re-run existing test suite to confirm no regressions**

```bash
docker-compose exec -T backend python -m pytest tests/ -q
```

Expected: `82 passed` (70 pre-existing + 12 new from Task 1)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/external/football_data.py
git commit -m "Add FootballDataClient HTTP methods (get_competition, get_matches, get_match)"
```

---

## Phase 2 — Fixture sync logic and CLI

### Task 3: Stage and group mapping helpers (TDD)

**Files:**
- Create: `backend/app/services/fixture_sync.py`
- Create: `backend/tests/test_fixture_sync.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_fixture_sync.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker-compose exec -T backend python -m pytest tests/test_fixture_sync.py -v
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Implement the mapping helpers**

Create `backend/app/services/fixture_sync.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker-compose exec -T backend python -m pytest tests/test_fixture_sync.py -v
```

Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/fixture_sync.py backend/tests/test_fixture_sync.py
git commit -m "Add fixture_sync stage and group mapping helpers"
```

---

### Task 4: `FixtureRecord` dataclass and `_record_from_match` (TDD)

**Files:**
- Modify: `backend/app/services/fixture_sync.py`
- Modify: `backend/tests/test_fixture_sync.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_fixture_sync.py`:

```python
from datetime import datetime, timezone

from app.models.fixture import MatchStatus
from app.services.fixture_sync import FixtureRecord, _record_from_match


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker-compose exec -T backend python -m pytest tests/test_fixture_sync.py::TestRecordFromMatch -v
```

Expected: `ImportError: cannot import name 'FixtureRecord' from 'app.services.fixture_sync'`

- [ ] **Step 3: Implement `FixtureRecord` and `_record_from_match`**

Append to `backend/app/services/fixture_sync.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.fixture import MatchStatus
from app.services.external.football_data import map_status


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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker-compose exec -T backend python -m pytest tests/test_fixture_sync.py -v
```

Expected: `13 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/fixture_sync.py backend/tests/test_fixture_sync.py
git commit -m "Add FixtureRecord and _record_from_match for resolved and null-team matches"
```

---

### Task 5: `SyncResult` dataclass and `_upsert_fixtures` (TDD)

**Files:**
- Modify: `backend/app/services/fixture_sync.py`
- Modify: `backend/tests/test_fixture_sync.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_fixture_sync.py`:

```python
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.competition import Competition
from app.models.fixture import Fixture
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
    *, ext: str, home: str = "Mexico", away: str = "South Africa",
    kickoff_iso: str = "2026-06-11T19:00:00+00:00", stage: str = "group", group: str | None = "A",
) -> FixtureRecord:
    return FixtureRecord(
        external_id=ext,
        home_team=home,
        away_team=away,
        kickoff=datetime.fromisoformat(kickoff_iso),
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
        changed = [_record(ext="1", kickoff_iso="2026-06-11T20:00:00+00:00")]
        result = await _upsert_fixtures(session, changed, competition.id)
        assert result.updated == 1
        assert result.changed_fields["kickoff"] == 1

    @pytest.mark.asyncio
    async def test_updates_team_resolution(self, session, competition) -> None:
        # Simulate a knockout slot getting a real team
        await _upsert_fixtures(
            session,
            [_record(ext="1", home="slot:round_of_32:1:home", away="slot:round_of_32:1:away", stage="round_of_32", group=None)],
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker-compose exec -T backend python -m pytest tests/test_fixture_sync.py::TestUpsertFixtures -v
```

Expected: `ImportError: cannot import name 'SyncResult'` (and friends).

- [ ] **Step 3: Implement `SyncResult` and `_upsert_fixtures`**

Append to `backend/app/services/fixture_sync.py`:

```python
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
            if new_val != old_val:
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
```

- [ ] **Step 4: Add `aiosqlite` for the in-memory test session**

```bash
docker-compose exec -T backend pip install --no-cache-dir aiosqlite
```

(This is a transient install in the running container, mirroring the pytest pattern.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker-compose exec -T backend python -m pytest tests/test_fixture_sync.py -v
```

Expected: `18 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/fixture_sync.py backend/tests/test_fixture_sync.py
git commit -m "Add SyncResult and _upsert_fixtures with insert/update/unchanged/db-only counts"
```

---

### Task 6: Sample test fixture and `sync_from_cache` (TDD)

**Files:**
- Create: `backend/tests/fixtures/wc2026_sample.json`
- Modify: `backend/app/services/fixture_sync.py`
- Modify: `backend/tests/test_fixture_sync.py`

- [ ] **Step 1: Create the sample test fixture**

Create `backend/tests/fixtures/wc2026_sample.json`:

```json
{
  "matches": [
    {
      "id": 1001, "utcDate": "2026-06-11T19:00:00Z", "status": "TIMED",
      "stage": "GROUP_STAGE", "group": "GROUP_A",
      "homeTeam": {"id": 769, "name": "Mexico", "shortName": "Mexico", "tla": "MEX"},
      "awayTeam": {"id": 774, "name": "South Africa", "shortName": "South Africa", "tla": "RSA"}
    },
    {
      "id": 1002, "utcDate": "2026-06-12T19:00:00Z", "status": "TIMED",
      "stage": "GROUP_STAGE", "group": "GROUP_B",
      "homeTeam": {"id": 759, "name": "Brazil", "shortName": "Brazil", "tla": "BRA"},
      "awayTeam": {"id": 763, "name": "Croatia", "shortName": "Croatia", "tla": "CRO"}
    },
    {
      "id": 1003, "utcDate": "2026-06-28T19:00:00Z", "status": "TIMED",
      "stage": "LAST_32", "group": null,
      "homeTeam": {"id": null, "name": null, "shortName": null, "tla": null},
      "awayTeam": {"id": null, "name": null, "shortName": null, "tla": null}
    },
    {
      "id": 1004, "utcDate": "2026-06-29T19:00:00Z", "status": "TIMED",
      "stage": "LAST_32", "group": null,
      "homeTeam": {"id": null, "name": null, "shortName": null, "tla": null},
      "awayTeam": {"id": null, "name": null, "shortName": null, "tla": null}
    },
    {
      "id": 1005, "utcDate": "2026-07-04T19:00:00Z", "status": "TIMED",
      "stage": "LAST_16", "group": null,
      "homeTeam": {"id": null, "name": null, "shortName": null, "tla": null},
      "awayTeam": {"id": null, "name": null, "shortName": null, "tla": null}
    },
    {
      "id": 1006, "utcDate": "2026-07-09T19:00:00Z", "status": "TIMED",
      "stage": "QUARTER_FINALS", "group": null,
      "homeTeam": {"id": null, "name": null, "shortName": null, "tla": null},
      "awayTeam": {"id": null, "name": null, "shortName": null, "tla": null}
    },
    {
      "id": 1007, "utcDate": "2026-07-18T19:00:00Z", "status": "TIMED",
      "stage": "THIRD_PLACE", "group": null,
      "homeTeam": {"id": null, "name": null, "shortName": null, "tla": null},
      "awayTeam": {"id": null, "name": null, "shortName": null, "tla": null}
    },
    {
      "id": 1008, "utcDate": "2026-07-19T19:00:00Z", "status": "TIMED",
      "stage": "FINAL", "group": null,
      "homeTeam": {"id": null, "name": null, "shortName": null, "tla": null},
      "awayTeam": {"id": null, "name": null, "shortName": null, "tla": null}
    }
  ]
}
```

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/test_fixture_sync.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
docker-compose exec -T backend python -m pytest tests/test_fixture_sync.py::TestSyncFromCache -v
```

Expected: `ImportError: cannot import name 'sync_from_cache'`

- [ ] **Step 4: Implement `sync_from_cache`**

Append to `backend/app/services/fixture_sync.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker-compose exec -T backend python -m pytest tests/test_fixture_sync.py -v
```

Expected: `20 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/fixture_sync.py backend/tests/fixtures/wc2026_sample.json backend/tests/test_fixture_sync.py
git commit -m "Add sync_from_cache and 8-match sample test fixture"
```

---

### Task 7: `sync_from_api` and flag-name validation

**Files:**
- Modify: `backend/app/services/fixture_sync.py`

**Note:** This wraps the API call + cache write, then delegates to the same `_upsert_fixtures`. Tested by the seed run in Phase 4 (no isolated unit test — would require mocking httpx).

- [ ] **Step 1: Implement `sync_from_api`**

Append to `backend/app/services/fixture_sync.py`:

```python
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
```

- [ ] **Step 2: Verify imports compile**

```bash
docker-compose exec -T backend python -c "from app.services.fixture_sync import sync_from_api, sync_from_cache, SyncResult; print('imports OK')"
```

Expected: `imports OK`

- [ ] **Step 3: Run full test suite**

```bash
docker-compose exec -T backend python -m pytest tests/ -q
```

Expected: `90 passed` (70 pre-existing + 12 from Task 1 + 8 from Tasks 3-6)

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/fixture_sync.py
git commit -m "Add sync_from_api with cache write and flags.ts mismatch detection"
```

---

### Task 8: `seed_fixtures.py` CLI

**Files:**
- Create: `backend/scripts/seed_fixtures.py`

- [ ] **Step 1: Create the CLI script**

Create `backend/scripts/seed_fixtures.py`:

```python
"""Seed WC2026 fixtures from Football-Data.org or a local JSON cache.

Default: fetch from API, write JSON cache, upsert into DB.
Use --from-cache to seed offline from the existing JSON.

Run with:
    docker-compose exec backend python -m scripts.seed_fixtures
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from app.config import get_settings
from app.models.competition import Competition
from app.services.fixture_sync import SyncResult, sync_from_api, sync_from_cache


DEFAULT_CACHE_PATH = Path(__file__).parent.parent / "data" / "wc2026_fixtures.json"
DEFAULT_COMPETITION_CODE = "WC"
DEFAULT_COMPETITION_NAME = "FIFA World Cup 2026"


async def _resolve_competition(session: AsyncSession, name: str) -> Competition:
    result = await session.execute(select(Competition).where(Competition.name == name))
    comp = result.scalar_one_or_none()
    if comp is not None:
        return comp
    comp = Competition(name=name)
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


def _print_result(result: SyncResult) -> None:
    print(f"Created:    {result.created}")
    print(f"Updated:    {result.updated}")
    print(f"Unchanged:  {result.unchanged}")
    print(f"DB-only:    {result.db_only_count}")
    if result.changed_fields:
        print(f"Changed fields: {dict(result.changed_fields)}")
    if result.unmatched_flag_teams:
        print(f"\nWARNING: {len(result.unmatched_flag_teams)} team names not present in frontend flags.ts:")
        for name in result.unmatched_flag_teams:
            print(f"  - {name!r}")


async def _main(args: argparse.Namespace) -> int:
    settings = get_settings()
    db_url = str(settings.database_url).replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(db_url)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        comp = await _resolve_competition(session, args.competition_name)

        cache_path = Path(args.cache_path)

        if args.from_cache:
            print(f"Seeding from cache: {cache_path}")
            result = await sync_from_cache(session, comp.id, cache_path)
        else:
            cache_arg = None if args.no_cache_write else cache_path
            print(f"Fetching from Football-Data ({args.competition_code})...")
            result = await sync_from_api(
                session,
                comp.id,
                competition_code=args.competition_code,
                cache_path=cache_arg,
            )
            if cache_arg is not None:
                print(f"Cache written: {cache_path}")

    _print_result(result)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-cache", action="store_true", help="Seed offline from existing JSON")
    parser.add_argument("--no-cache-write", action="store_true", help="Call API but don't update cache")
    parser.add_argument("--cache-path", default=str(DEFAULT_CACHE_PATH))
    parser.add_argument("--competition-code", default=DEFAULT_COMPETITION_CODE)
    parser.add_argument("--competition-name", default=DEFAULT_COMPETITION_NAME)
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI parses**

```bash
docker-compose exec -T backend python -m scripts.seed_fixtures --help
```

Expected: argparse help text printed; exits 0.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/seed_fixtures.py
git commit -m "Add seed_fixtures CLI wrapper for sync_from_api and sync_from_cache"
```

---

## Phase 3 — Refactor `external_scores.py` onto the shared client (alpha)

### Task 9: Smoke test for refactored provider

**Files:**
- Create: `backend/tests/test_external_scores.py`

**Why a smoke test before the refactor:** there are no existing tests for `external_scores.py`, so we'd be refactoring without a regression net. Adding a small test against the cached probe data first means we can detect regressions during the refactor.

- [ ] **Step 1: Write the smoke test**

Create `backend/tests/test_external_scores.py`:

```python
"""Smoke tests for the refactored FootballDataScoreProvider."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.models.fixture import MatchStatus


PROBE_MATCHES = json.loads(
    (Path(__file__).parent.parent / "data" / "probe" / "fd_matches.json").read_text()
)["matches"]


@pytest.mark.asyncio
async def test_fetch_live_scores_maps_match_to_external_score() -> None:
    """When the API returns a real (resolved) match, we get a populated ExternalScore."""
    from app.services.external_scores import FootballDataScoreProvider

    sample = next(m for m in PROBE_MATCHES if m["stage"] == "GROUP_STAGE" and m["homeTeam"]["name"])

    with patch("app.services.external_scores.FootballDataClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.get_matches = AsyncMock(return_value=[sample])
        provider = FootballDataScoreProvider()
        scores = await provider.fetch_live_scores("WC")

    assert len(scores) == 1
    s = scores[0]
    assert s.external_id == str(sample["id"])
    assert s.home_team == sample["homeTeam"]["name"]
    assert s.away_team == sample["awayTeam"]["name"]
    assert s.status == MatchStatus.SCHEDULED  # TIMED → SCHEDULED


@pytest.mark.asyncio
async def test_fetch_live_scores_filters_by_status() -> None:
    """The provider passes the live-status filter through to get_matches."""
    from app.services.external_scores import FootballDataScoreProvider

    with patch("app.services.external_scores.FootballDataClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.get_matches = AsyncMock(return_value=[])
        provider = FootballDataScoreProvider()
        await provider.fetch_live_scores("WC")
        mock_client.get_matches.assert_awaited_once_with("WC", status="LIVE,IN_PLAY,PAUSED")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker-compose exec -T backend python -m pytest tests/test_external_scores.py -v
```

Expected: `ImportError: cannot import name 'FootballDataScoreProvider'` (current name is `FootballDataProvider`).

- [ ] **Step 3: Commit (test only, will pass after Task 10)**

```bash
git add backend/tests/test_external_scores.py
git commit -m "Add smoke tests for refactored FootballDataScoreProvider (will pass after refactor)"
```

---

### Task 10: Refactor `external_scores.py`

**Files:**
- Modify: `backend/app/services/external_scores.py`

- [ ] **Step 1: Replace the file with the refactored version**

Overwrite `backend/app/services/external_scores.py`:

```python
"""External score fetching service.

Fetches live scores from Football-Data.org via the shared FootballDataClient.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.fixture import MatchStatus
from app.services.external.football_data import FootballDataClient, map_status


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
    home_score_et: int | None = None
    away_score_et: int | None = None
    home_penalties: int | None = None
    away_penalties: int | None = None


class ScoreProviderBase(ABC):
    """Base class for score providers (kept abstract for testability)."""

    @abstractmethod
    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        ...

    @abstractmethod
    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        ...


class FootballDataScoreProvider(ScoreProviderBase):
    """Live-score provider using football-data.org via the shared client."""

    LIVE_STATUS_FILTER = "LIVE,IN_PLAY,PAUSED"

    def __init__(self, client: FootballDataClient | None = None) -> None:
        self._client = client or FootballDataClient()

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        """Fetch live scores for a competition (e.g. competition_id='WC')."""
        matches = await self._client.get_matches(competition_id, status=self.LIVE_STATUS_FILTER)
        return [self._to_external_score(m) for m in matches]

    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        match = await self._client.get_match(fixture_id)
        if match is None:
            return None
        return self._to_external_score(match)

    @staticmethod
    def _to_external_score(match: dict) -> ExternalScore:
        score = match.get("score") or {}
        full_time = score.get("fullTime") or {}
        extra_time = score.get("extratime") or score.get("extraTime") or {}
        penalty = score.get("penalty") or score.get("penalties") or {}
        home_team = match.get("homeTeam") or {}
        away_team = match.get("awayTeam") or {}

        return ExternalScore(
            external_id=str(match.get("id", "")),
            home_team=home_team.get("name") or "",
            away_team=away_team.get("name") or "",
            home_score=full_time.get("home") or 0,
            away_score=full_time.get("away") or 0,
            status=map_status(match.get("status", "")),
            minute=match.get("minute"),
            home_score_et=extra_time.get("home"),
            away_score_et=extra_time.get("away"),
            home_penalties=penalty.get("home"),
            away_penalties=penalty.get("away"),
        )


def get_score_provider() -> ScoreProviderBase:
    """Return the configured score provider.

    Single-provider since we standardised on Football-Data.org. Kept as a
    function (rather than inlined at the call site) for ease of swapping
    providers in the future.
    """
    return FootballDataScoreProvider()
```

- [ ] **Step 2: Run the new smoke tests**

```bash
docker-compose exec -T backend python -m pytest tests/test_external_scores.py -v
```

Expected: `2 passed`

- [ ] **Step 3: Run the full test suite**

```bash
docker-compose exec -T backend python -m pytest tests/ -q
```

Expected: `92 passed` (90 from before + 2 new). All previous tests still pass.

- [ ] **Step 4: Verify the admin import surface still works**

```bash
docker-compose exec -T backend python -c "from app.api.admin import router; from app.services.external_scores import get_score_provider, ExternalScore; print('admin imports OK')"
```

Expected: `admin imports OK` (no `APIFootballProvider` or `ScoreProvider` enum referenced in `admin.py`, so it doesn't need updating — verify by grep in step 5).

- [ ] **Step 5: Confirm `admin.py` doesn't reference removed names**

```bash
grep -nE 'APIFootballProvider|ScoreProvider\b|PROVIDERS\[' /Users/lukeaarohi/pyfiles/predictorv2/backend/app/api/admin.py
```

Expected: no output (admin.py only used `get_score_provider` and `ExternalScore`, both preserved).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/external_scores.py
git commit -m "Refactor external_scores.py onto shared FootballDataClient; drop APIFootballProvider"
```

---

## Phase 4 — Run the seed

### Task 11: Wipe placeholder data and run seed_fixtures

**Files:**
- (DB only — no source files modified)

- [ ] **Step 1: Verify current DB state (before wipe)**

```bash
docker-compose exec -T backend python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    e = create_async_engine('postgresql+asyncpg://predictor:predictor@db:5432/predictor')
    async with e.begin() as c:
        for tbl in ['competitions','fixtures','match_predictions','team_predictions','users','scores']:
            r = await c.execute(text(f'SELECT count(*) FROM {tbl}'))
            print(f'{tbl}: {r.scalar()}')

asyncio.run(main())
"
```

Expected: roughly `competitions: 1, fixtures: 88, match_predictions: 95, team_predictions: 220, users: 24, scores: 72` (approximately — exact numbers don't matter).

- [ ] **Step 2: Run the one-off cleanup**

```bash
docker-compose exec -T backend python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    e = create_async_engine('postgresql+asyncpg://predictor:predictor@db:5432/predictor')
    async with e.begin() as c:
        for stmt in [
            'DELETE FROM scores',
            'DELETE FROM match_predictions',
            'DELETE FROM team_predictions',
            'DELETE FROM fixtures',
        ]:
            r = await c.execute(text(stmt))
            print(f'{stmt}: {r.rowcount} rows')

asyncio.run(main())
"
```

Expected: ~72 / ~95 / ~220 / ~88 rows deleted respectively.

- [ ] **Step 3: Run the seed**

```bash
docker-compose exec -T backend python -m scripts.seed_fixtures
```

Expected output (approximately):
```
Fetching from Football-Data (WC)...
Cache written: /app/data/wc2026_fixtures.json
Created:    104
Updated:    0
Unchanged:  0
DB-only:    0
```

(Plus a possible warning block if any team names aren't in `flags.ts`.)

- [ ] **Step 4: Verify the DB now has 104 fixtures**

```bash
docker-compose exec -T backend python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    e = create_async_engine('postgresql+asyncpg://predictor:predictor@db:5432/predictor')
    async with e.begin() as c:
        r = await c.execute(text('SELECT stage, count(*) FROM fixtures GROUP BY stage ORDER BY stage'))
        for row in r:
            print(row)

asyncio.run(main())
"
```

Expected:
```
('final', 1)
('group', 72)
('quarter_final', 4)
('round_of_16', 8)
('round_of_32', 16)
('semi_final', 2)
('third_place', 1)
```

- [ ] **Step 5: Re-run the seed to confirm idempotency**

```bash
docker-compose exec -T backend python -m scripts.seed_fixtures
```

Expected:
```
Created:    0
Updated:    0
Unchanged:  104
```

- [ ] **Step 6: Spot-check 3 fixtures by hand**

```bash
docker-compose exec -T backend python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    e = create_async_engine('postgresql+asyncpg://predictor:predictor@db:5432/predictor')
    async with e.begin() as c:
        r = await c.execute(text(\"SELECT home_team, away_team, kickoff, stage, \\\"group\\\" FROM fixtures WHERE stage='group' ORDER BY kickoff LIMIT 3\"))
        for row in r:
            print(row)

asyncio.run(main())
"
```

Expected: First three group-stage fixtures by kickoff. Cross-check kickoff date/time + teams against fifa.com or Wikipedia's "2026 FIFA World Cup group stage" page.

If the spot-check passes, the seed is correct. If teams or times are off, halt and investigate before proceeding.

---

### Task 12: Commit the seed cache snapshot

**Files:**
- Add: `backend/data/wc2026_fixtures.json`

- [ ] **Step 1: Verify the cache file was written and is in `backend/data/`**

```bash
ls -la /Users/lukeaarohi/pyfiles/predictorv2/backend/data/wc2026_fixtures.json
```

Expected: file exists, ~150KB.

- [ ] **Step 2: Commit the cache as the auditable seed snapshot**

```bash
git add backend/data/wc2026_fixtures.json
git commit -m "Seed cache: 104 WC2026 fixtures from Football-Data.org as of 2026-05-09"
```

---

## Phase 5 — Cleanup

### Task 13: Remove API-Football leftovers

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `docker-compose.yml`
- Modify: `.env` (local — sed to remove the line)

- [ ] **Step 1: Remove from `backend/app/config.py`**

Edit `backend/app/config.py` — delete these three lines:

```python
    # API-Football (api-sports.io)
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
```

- [ ] **Step 2: Remove from `backend/.env.example`**

Edit `backend/.env.example` — delete these three lines:

```
# API-Football / api-sports.io (optional)
API_FOOTBALL_KEY=

```

(Leave the `# Football-Data.org` block intact.)

- [ ] **Step 3: Remove from `docker-compose.yml`**

Edit `docker-compose.yml:33` — delete this single line:

```
      - API_FOOTBALL_KEY=${API_FOOTBALL_KEY:-}
```

- [ ] **Step 4: Remove from local `.env` via sed (no value exposure)**

```bash
sed -i '' '/^API_FOOTBALL_KEY=/d' /Users/lukeaarohi/pyfiles/predictorv2/.env
sed -i '' '/^# API-Football (optional)$/d' /Users/lukeaarohi/pyfiles/predictorv2/.env
grep -E '^(API_FOOTBALL|FOOTBALL_DATA)' /Users/lukeaarohi/pyfiles/predictorv2/.env | cut -d= -f1
```

Expected output: only `FOOTBALL_DATA_TOKEN` (no `API_FOOTBALL_KEY`).

- [ ] **Step 5: Run pytest to confirm nothing broke**

```bash
docker-compose exec -T backend python -m pytest tests/ -q
```

Expected: `92 passed`

- [ ] **Step 6: Commit (excluding `.env` which is gitignored)**

```bash
git add backend/app/config.py backend/.env.example docker-compose.yml
git commit -m "Drop dead-end API-Football config now that we've committed to Football-Data"
```

---

## Verification gate (final)

- [ ] **Run full test suite one last time**

```bash
docker-compose exec -T backend python -m pytest tests/ -q
```

Expected: `92 passed` (70 pre-existing + 12 from Task 1 + 8 from Tasks 3-7 + 2 from Task 9).

- [ ] **Run the seed once more from cache to confirm offline path works**

```bash
docker-compose exec -T backend python -m scripts.seed_fixtures --from-cache
```

Expected:
```
Seeding from cache: /app/data/wc2026_fixtures.json
Created:    0
Updated:    0
Unchanged:  104
```

- [ ] **Confirm git log shows clean linear history**

```bash
git log --oneline -15
```

Expected: 13 new commits (one per task), each with a descriptive message starting with the change verb.

---

## Notes

- **Pytest in container:** the running `backend` container needs pytest installed once per rebuild. If you see `No module named pytest`, run `docker-compose exec -T backend pip install --no-cache-dir 'pytest>=7.4.0' 'pytest-asyncio>=0.23.0' aiosqlite` and retry.
- **API quota:** Football-Data Free tier is 10 calls/min. Seed uses 1 call, so plenty of headroom. If you re-run the seed many times during testing, prefer `--from-cache` to avoid burning quota.
- **Schema additions:** `Fixture.stage` already accepts `"third_place"` (free-form string column). No Alembic migration needed.
- **What this plan does NOT do:** Phase 4 live-scoring polling, frontend handling of placeholder team strings, `flags.ts` updates for unmatched names, or any post-launch enhancements listed in the spec's "Future considerations".

# WC2026 Fixtures Seeding — Design Spec

**Date**: 2026-05-02 (revised 2026-05-09 after API probe)
**Status**: Approved (pending final spec review)
**Owner**: Luke Aarohi

## Goal

Replace the placeholder `seed_data.py` test data with the **real, finalised** 2026 FIFA World Cup fixtures and teams, sourced from **Football-Data.org**. Seed all 104 matches (groups + every knockout round including the third-place playoff) with placeholder team strings for unresolved knockouts; live-scoring will mirror Football-Data's team-name resolutions back into the DB as group results determine knockout matchups.

The seeding script is the *first consumer* of a Football-Data.org integration that will be reused, in Phase 4, by the live-scoring sync.

## Locked-in decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Existing data | Wipe and rebuild (one-time) | Test predictions reference placeholder fixtures; no value in preserving |
| Source of truth | **Football-Data.org**, hybrid (fetch → JSON cache → DB) | Free tier covers full WC2026 dataset (probe-verified); same API as live-scoring |
| Scope | All 104 fixtures incl. third-place | Complete tournament structure on day one |
| Idempotency | Upsert by `external_id`, never destructive | Safe re-runs; handles kickoff changes without losing predictions |
| `--wipe` flag | **Not in script** | Destructive ops live separately; one-off SQL handles first-run cleanup |
| Third-place match | Included as new stage `"third_place"` | Football-Data exposes it as a first-class `THIRD_PLACE` stage |
| API auth | `X-Auth-Token` header from `Settings.football_data_token` | Env var: `FOOTBALL_DATA_TOKEN` |

### Why Football-Data.org over API-Football

Probed both. API-Football's Free tier rejects season `2026` (`"Free plans do not have access to this season, try from 2022 to 2024."`); Football-Data.org's Free tier returns all 104 WC2026 matches with full data. Cost-free, identical-API plan for live-scoring later.

## Architecture

```
backend/
├── app/services/external/
│   ├── __init__.py
│   └── football_data.py        # HTTP client (~80 lines)
├── app/services/
│   └── fixture_sync.py         # Business logic (~120 lines, simpler than original)
├── scripts/
│   ├── seed_fixtures.py        # CLI wrapper (~100 lines)
│   └── probe_football_data.py  # Discovery tool (already written, kept as reference)
├── data/
│   ├── wc2026_fixtures.json    # Seed cache, committed to git
│   └── probe/                  # Raw API discovery responses (committed for audit)
│       ├── fd_competition.json
│       ├── fd_matches.json
│       └── fd_teams.json
└── tests/
    ├── fixtures/wc2026_sample.json
    └── test_fixture_sync.py
```

### `app/services/external/football_data.py`

Thin async HTTP client for football-data.org/v4. Reads `Settings.football_data_token` for auth and `Settings.football_data_base_url` for the host. Tournament-agnostic: takes a competition code (e.g. `"WC"`).

**Public interface:**

```python
class FootballDataClient:
    async def get_competition(self, code: str) -> dict
    async def get_matches(self, code: str) -> list[dict]
    async def get_teams(self, code: str) -> list[dict]
```

**Behaviour:**

- Auth header: `X-Auth-Token: <football_data_token>`
- Network timeout: 15s per request
- Retries: up to 3 attempts on network errors with exponential backoff (1s, 4s, 9s)
- Rate limit (HTTP 429): one retry honouring `X-RequestCounter-Reset` if present, then raise
- Errors raised as domain exceptions:
  - `FootballDataAuthError` (401, 403)
  - `FootballDataRateLimitError` (429 after retry)
  - `FootballDataError` (catch-all)

### `app/services/fixture_sync.py`

Pure business logic that maps Football-Data JSON → `Fixture` rows. Imports the API client; does **not** import `Settings`. The caller (CLI or Phase 4 live-scoring scheduler) passes session and competition_id.

**Public interface:**

```python
async def sync_from_api(
    session: AsyncSession,
    competition_id: UUID,
    *,
    competition_code: str = "WC",
    cache_path: Path | None = None,
) -> SyncResult

async def sync_from_cache(
    session: AsyncSession,
    competition_id: UUID,
    cache_path: Path,
) -> SyncResult
```

**Internal helpers:**

- `_map_stage(api_stage: str) -> str` — see "Stage mapping" table below.
- `_map_status(api_status: str) -> MatchStatus` — see "Status mapping" table below.
- `_map_group(api_group: str | None) -> str | None` — `"GROUP_A"` → `"A"`, `None` → `None`.
- `_record_from_match(match_dict: dict) -> FixtureRecord` — produces a normalised dataclass.
- `_upsert_fixtures(session, records, competition_id) -> SyncResult` — diff against DB, INSERT/UPDATE.

**Returns** `SyncResult`:

```python
@dataclass
class SyncResult:
    created: int
    updated: int
    unchanged: int
    db_only_count: int                   # in DB but not in API (warning, not deleted)
    changed_fields: dict[str, int]       # e.g. {"kickoff": 3, "home_team": 16}
    unmatched_flag_teams: list[str]      # teams whose name doesn't match flags.ts keys
```

### `scripts/seed_fixtures.py`

Argparse CLI wrapper. Resolves the competition (creates if missing), calls one of `sync_from_api` / `sync_from_cache`, prints `SyncResult` summary.

**CLI:**

```bash
docker-compose exec backend python -m scripts.seed_fixtures
  [--from-cache]                 # skip API call, use existing JSON
  [--no-cache-write]             # call API but don't update cache
  [--cache-path PATH]            # default: backend/data/wc2026_fixtures.json
  [--competition-code STR]       # default: WC (Football-Data competition code)
  [--competition-name STR]       # default: "FIFA World Cup 2026" (DB row label)
```

Default behaviour: fetch from API, write to cache, upsert into DB. Safely re-runnable.

(Compared to the original draft: `--league` and `--season` flags removed because Football-Data identifies the tournament by competition code and uses the competition's `currentSeason` automatically.)

## Data flow

### Default flow

```
[CLI] → [football_data.get_matches("WC")]
     → [write JSON to backend/data/wc2026_fixtures.json]
     → [fixture_sync._upsert (no parsing — clean enums)]
     → [print SyncResult]
```

### Offline / re-seed from cache (`--from-cache`)

```
[CLI] → [read backend/data/wc2026_fixtures.json]
     → [fixture_sync._upsert]
     → [print SyncResult]
```

### First-run cleanup (one-off, performed manually before first seed)

```sql
DELETE FROM scores;
DELETE FROM match_predictions;
DELETE FROM team_predictions;
DELETE FROM fixtures;
-- competitions and users untouched
```

This is **not** committed as a script. One-time bootstrap step we run by hand and then never again.

## API integration details

### Endpoints used

| Endpoint | Purpose | Calls per run |
|----------|---------|---------------|
| `GET /v4/competitions/WC` | Competition metadata, current season info | 1 (optional sanity check) |
| `GET /v4/competitions/WC/matches` | All 104 matches | 1 |
| `GET /v4/competitions/WC/teams` | 48 teams (name validation against `flags.ts`) | 1 |

Two-three API calls per fetch run; rate limit is 10/min on Free tier — comfortably under.

### Verified response shape (from 2026-05-09 probe)

`GET /v4/competitions/WC/matches` returns:

```json
{
  "filters": { ... },
  "resultSet": {"count": 104, "first": "2026-06-11", "last": "2026-07-19", "played": 0},
  "competition": { "id": 2000, "name": "FIFA World Cup", "code": "WC", ... },
  "matches": [
    {
      "id": 537327,
      "utcDate": "2026-06-11T19:00:00Z",
      "status": "TIMED",
      "matchday": 1,
      "stage": "GROUP_STAGE",
      "group": "GROUP_A",
      "lastUpdated": "2025-12-06T20:20:44Z",
      "homeTeam": {"id": 769, "name": "Mexico", "shortName": "Mexico", "tla": "MEX", "crest": "https://crests.football-data.org/769.svg"},
      "awayTeam": {"id": 774, "name": "South Africa", "shortName": "South Africa", "tla": "RSA", "crest": "https://crests.football-data.org/9396.svg"},
      "score": {"winner": null, "duration": "REGULAR", "fullTime": {...}, "halfTime": {...}},
      "venue": null,
      "odds": {"msg": "Activate Odds-Package..."},
      "referees": []
    }
    // ... 103 more
  ]
}
```

Knockout fixtures with unresolved teams (probe-confirmed):

```json
{
  "id": 537417,
  "utcDate": "2026-06-28T19:00:00Z",
  "status": "TIMED",
  "matchday": null,
  "stage": "LAST_32",
  "group": null,
  "homeTeam": {"id": null, "name": null, "shortName": null, "tla": null, "crest": null},
  "awayTeam": {"id": null, "name": null, "shortName": null, "tla": null, "crest": null}
}
```

All `homeTeam` / `awayTeam` fields are `null` when the team is undetermined. We synthesize a placeholder team string in `home_team`/`away_team` (see "Placeholder names" below).

### Field mapping (Football-Data → `Fixture`)

| Fixture column | Source | Notes |
|----------------|--------|-------|
| `external_id` | `str(match.id)` | Football-Data match ID, stable across runs |
| `home_team` | `match.homeTeam.name` if present else synthesised slot | See "Placeholder names" |
| `away_team` | `match.awayTeam.name` if present else synthesised slot | See "Placeholder names" |
| `kickoff` | parsed `match.utcDate` → UTC datetime | Already UTC, ISO 8601 |
| `stage` | `_map_stage(match.stage)` | Direct enum lookup, no parsing |
| `group` | `_map_group(match.group)` | `"GROUP_A"` → `"A"`, `None` for knockouts |
| `match_number` | 1-indexed sequence per stage, sorted by `kickoff` ascending | e.g. group: 1-72, round_of_32: 1-16, ..., final: 1 |
| `status` | `_map_status(match.status)` | See "Status mapping" |
| `competition_id` | resolved from `--competition-name` lookup/create | Set by CLI |

### Stage mapping (`_map_stage`)

| API `match.stage` | `Fixture.stage` |
|-------------------|------------------|
| `GROUP_STAGE` | `"group"` |
| `LAST_32` | `"round_of_32"` |
| `LAST_16` | `"round_of_16"` |
| `QUARTER_FINALS` | `"quarter_final"` |
| `SEMI_FINALS` | `"semi_final"` |
| `THIRD_PLACE` | `"third_place"` |
| `FINAL` | `"final"` |
| anything else | raises `UnknownStageError(api_stage)` |

The probe confirmed exactly these 7 stage values in the WC2026 response — no others appear.

### Status mapping (`_map_status`)

| API `match.status` | `MatchStatus` |
|--------------------|----------------|
| `SCHEDULED`, `TIMED` | `SCHEDULED` |
| `IN_PLAY`, `EXTRA_TIME`, `PENALTY_SHOOTOUT` | `LIVE` |
| `PAUSED` | `HALFTIME` |
| `FINISHED`, `AWARDED` | `FINISHED` |
| `POSTPONED`, `SUSPENDED` | `POSTPONED` |
| `CANCELLED` | `CANCELLED` |
| anything else | `SCHEDULED` (with warning log) |

The probe shows all 104 fixtures currently `TIMED`. Live-scoring later will see `IN_PLAY`, `FINISHED`, etc. on the same path.

### Group mapping (`_map_group`)

Trivial — strip the `"GROUP_"` prefix.

```python
def _map_group(api_group: str | None) -> str | None:
    if api_group is None:
        return None
    if api_group.startswith("GROUP_"):
        return api_group.removeprefix("GROUP_")  # "A".."L"
    raise UnknownGroupError(api_group)
```

The probe confirmed all 12 group values are `GROUP_A` through `GROUP_L`. No other formats appear.

### Placeholder names for unresolved knockouts

When `homeTeam.name is None` (or away):

```python
home_team = f"slot:{stage}:{external_id}:home"  # e.g. "slot:round_of_32:537417:home"
```

These strings are unique (external_id ensures uniqueness), easy to spot in the UI as unresolved, and will be overwritten by the live-scoring sync calling the same `_upsert_fixtures` path once Football-Data resolves the team.

### New stage value: `"third_place"`

Adds a new value to the recognised set for `Fixture.stage`. The column is a free-form string with no DB-level constraint, so this is a data change, not a schema change. **No Alembic migration required.**

Whether to expose the third-place match in the predictor UI is a separate decision deferred by the user.

### Schema migration impact

**None.** All data fields map to existing columns; `Fixture.stage` accepts the new `"third_place"` value as-is.

## DB operations

Single transaction, in this order:

```python
existing = {f.external_id: f for f in await load_fixtures(session, competition_id)}
records = [_record_from_match(m) for m in api_matches]

for rec in records:
    if rec.external_id in existing:
        f = existing[rec.external_id]
        changed = diff_and_apply(f, rec)   # compares: kickoff, home_team, away_team, status, stage, group, match_number
        if changed: updated += 1
        else: unchanged += 1
    else:
        session.add(Fixture(**rec.to_kwargs(competition_id=competition_id)))
        created += 1

# DB-only fixtures (in DB, not in API): logged as warning, never deleted
db_only = set(existing.keys()) - {r.external_id for r in records}

await session.commit()
```

### Idempotency contract

- Empty DB + 104 records → 104 created, 0 updated, 0 unchanged
- Same input twice → 0 created, 0 updated, 104 unchanged
- API kickoff change → 1 updated; predictions/scores untouched
- API team-name resolution (`"slot:..."` → `"USA"`) → 1 updated; **same path used by live-scoring**
- API removes a fixture → DB row preserved, warning logged. Pruning is intentionally not implemented.

## First-run cleanup

Run **once**, manually, before the first `seed_fixtures` call:

```bash
docker-compose exec backend python -c "
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

Expected output: `~72 / ~95 / ~220 / ~88` rows deleted respectively.

## Edge cases and error handling

| Scenario | Behaviour |
|----------|-----------|
| HTTP 401/403 (bad/missing key) | Raise `FootballDataAuthError` |
| HTTP 429 (rate limit) | Retry once after `X-RequestCounter-Reset`; then raise `FootballDataRateLimitError` |
| Network timeout | 3 retries with backoff (1s, 4s, 9s) |
| `matches: []` (zero matches) | Raise `FootballDataEmptyResponseError` (likely wrong competition code) |
| `--from-cache` and file missing | Raise `FileNotFoundError` with path |
| Unknown `match.stage` value | Raise `UnknownStageError` — abort entire run |
| Unknown `match.group` format | Raise `UnknownGroupError` — abort entire run |
| Team name not in `flags.ts` | Log warning, include in `SyncResult.unmatched_flag_teams`, do not fail |
| Malformed JSON in cache | Raise `ValueError` from JSON parser |
| Mid-seed exception | Transaction rollback, DB unchanged |

### Flag-name mismatch handling

After upsert, the script extracts unique non-placeholder team names from the seeded fixtures and cross-references against keys in `frontend/src/lib/utils/flags.ts`. Mismatches are summarised:

```
Warning: 2 team names not present in frontend flags.ts:
  - "Korea Republic" (consider alias for "South Korea")
  - "IR Iran" (consider alias for "Iran")
```

Non-blocking. Resolving mismatches is a follow-up frontend task.

## Testing

`backend/tests/test_fixture_sync.py`:

- `test_map_stage_all_seven_values` — every observed stage maps correctly
- `test_map_stage_unknown_raises`
- `test_map_status_known_codes`
- `test_map_status_unknown_falls_back_to_scheduled`
- `test_map_group_strips_prefix`
- `test_map_group_none_returns_none`
- `test_map_group_unknown_format_raises`
- `test_record_from_match_resolved_teams` — group fixture with real teams
- `test_record_from_match_null_teams_synthesises_slots` — knockout fixture with null teams
- `test_upsert_inserts_new_fixtures` — empty DB + 8 records → 8 created
- `test_upsert_updates_kickoff_change` — 1 existing, kickoff differs → 1 updated
- `test_upsert_updates_team_resolution` — `"slot:..."` → `"USA"` triggers update; predictions on the fixture untouched
- `test_upsert_skips_unchanged` — same input twice → 0 changes
- `test_upsert_db_only_logs_warning` — DB has fixture not in API → not deleted, warning recorded
- `test_sync_from_cache_reads_json` — happy path
- `test_unmatched_flag_teams_collected` — team name not in flags.ts list → recorded in result

**Test fixture:** `backend/tests/fixtures/wc2026_sample.json` — 8 hand-crafted matches modelled exactly on the probe response shape: 2 group stage (with real teams), 2 LAST_32 (with null teams), 1 LAST_16, 1 QUARTER_FINALS, 1 THIRD_PLACE, 1 FINAL.

**Skipped (intentional):**

- `football_data.py` HTTP client unit tests — thin wrapper, integration-tested by the first real seed run
- Full integration test against the live API — costs daily quota; one-off sanity check during implementation suffices

## Out of scope

- Live-scoring sync (Phase 4 work). `fixture_sync.sync_from_api` is the integration point.
- Auto-resolution of placeholder team strings in our DB (handled by live-scoring sync mirroring API state).
- Score data ingestion — Phase 4.
- Frontend `flags.ts` updates for newly-introduced team-name aliases — follow-up task once the warning list is reviewed.
- Adding a `competition_id` FK to `team_predictions` — long-term schema cleanup.
- A `--prune` flag for deleting DB-only fixtures — explicitly deferred.
- `tla` (3-letter abbreviation) integration into the schema — Football-Data exposes a stable 3-letter code per team (`MEX`, `RSA`, etc.) which would be more durable than full names for `flags.ts` keying. Future enhancement.
- Removing the dead-end API-Football integration (`api_football_key`, `api_football_base_url` settings) — kept for now in case of future need; can be cleaned up later if confirmed unused.

## Future considerations

- **`--prune` flag** for cases where Football-Data actually removes a fixture (unexpected). Would require explicit confirmation given the destructive cascade.
- **`competition_id` FK on `team_predictions`** — would let `team_predictions` deletion be scoped per-competition.
- **Venue field** — `venue` is `null` for all WC2026 matches on the Free tier. May be populated closer to kickoff or on a paid tier; currently we don't store it.
- **TLA codes** — Football-Data exposes stable 3-letter codes (`MEX`, `RSA`, `URY`). Could replace full team names as the canonical key joining `Fixture.home_team` to `flags.ts`. Reduces fragility; deferred.
- **Football-Data Free tier ceiling** — 10 calls/min suffices for WC live-scoring at sane poll rates (12 simultaneous matches × 1 call every 60s = 12 calls/min, just over the limit). May need a tier upgrade *or* batched single-call polling (`/v4/competitions/WC/matches?status=IN_PLAY`) which returns all live matches in one request. Verify in Phase 4.

## Implementation checklist (for the plan)

1. Create `app/services/external/__init__.py` and `football_data.py` with the HTTP client + domain exceptions.
2. Create `app/services/fixture_sync.py` with mapping helpers, upsert, `SyncResult`, and `sync_from_api` / `sync_from_cache` entry points.
3. `backend/data/` directory exists; ensure it's volume-mounted (already done in `docker-compose.yml`).
4. Create `scripts/seed_fixtures.py` CLI wrapper.
5. Add `backend/tests/fixtures/wc2026_sample.json` (modelled on probe response shape) and `test_fixture_sync.py`.
6. Run first-run cleanup SQL (manual one-off).
7. Run `python -m scripts.seed_fixtures` and inspect `SyncResult`.
8. Spot-check 3 fixtures in the DB by hand against fifa.com / Wikipedia.
9. Commit `wc2026_fixtures.json` to git as the auditable seed snapshot.
10. Commit `backend/data/probe/*.json` as audit trail of the discovery (optional but recommended).

# WC2026 Fixtures Seeding — Design Spec

**Date**: 2026-05-02
**Status**: Approved (pending final spec review)
**Owner**: Luke Aarohi

## Goal

Replace the placeholder `seed_data.py` test data with the **real, finalised** 2026 FIFA World Cup fixtures and teams, sourced from API-Football. Seed all 104 matches (groups + every knockout round including the third-place playoff) with placeholder team strings for unresolved knockouts; live-scoring will mirror API-Football's team-name resolutions back into the DB as group results determine knockout matchups.

The seeding script becomes the *first consumer* of an API-Football integration that will be reused, in Phase 4, by the live-scoring sync.

## Locked-in decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Existing data | Wipe and rebuild (one-time) | Test predictions reference placeholder fixtures; no value in preserving |
| Source of truth | API-Football, hybrid (fetch → JSON cache → DB) | Same API as live-scoring; deterministic re-runs from cache |
| Scope | All 104 fixtures incl. third-place | Complete tournament structure on day one |
| Idempotency | Upsert by `external_id`, never destructive | Safe re-runs; handles kickoff changes without losing predictions |
| `--wipe` flag | **Not in script** | Destructive ops live separately; one-off SQL handles first-run cleanup |
| Third-place match | Included as new stage `"third_place"` | One fixture, complete coverage; predictor inclusion TBD by user |

## Architecture

```
backend/
├── app/services/external/
│   ├── __init__.py
│   └── football_api.py        # HTTP client (~80 lines)
├── app/services/
│   └── fixture_sync.py        # Business logic (~150 lines)
├── scripts/
│   └── seed_fixtures.py       # CLI wrapper (~100 lines)
├── data/
│   └── wc2026_fixtures.json   # Cached API response, committed to git
└── tests/
    ├── fixtures/wc2026_sample.json
    └── test_fixture_sync.py
```

### `app/services/external/football_api.py`

Thin async HTTP client wrapping api-sports.io. Tournament-agnostic: takes `(league, season)` arguments. Reads `Settings.api_football_key` and `Settings.api_football_base_url`.

**Public interface:**

```python
class FootballAPI:
    async def get_status(self) -> dict
    async def get_fixtures(self, league: int, season: int) -> list[dict]
    async def get_teams(self, league: int, season: int) -> list[dict]
```

**Behaviour:**

- Auth header `x-apisports-key` from settings
- Network timeout: 10s per request
- Retries: up to 3 attempts on network errors with exponential backoff (1s, 4s, 9s)
- Rate limit (HTTP 429): one retry honouring `Retry-After`, then raise
- Errors raised as domain exceptions (not raw `httpx`):
  - `FootballAPIAuthError` (401, 403)
  - `FootballAPIRateLimitError` (429 after retry)
  - `FootballAPIError` (catch-all for other failures)

### `app/services/fixture_sync.py`

Pure business logic that maps API JSON → `Fixture` rows. Imports the API client; does **not** import `Settings` (caller passes session and competition_id).

**Public interface:**

```python
async def sync_from_api(
    session: AsyncSession,
    competition_id: UUID,
    *,
    league: int,
    season: int,
    cache_path: Path | None = None,
) -> SyncResult

async def sync_from_cache(
    session: AsyncSession,
    competition_id: UUID,
    cache_path: Path,
) -> SyncResult
```

**Internal helpers:**

- `_parse_round(api_round: str) -> tuple[str, str | None]` — round string → `(stage, group_letter)`. Group letter is usually derived separately (see "Group inference" below); this helper returns `None` for that field.
- `_parse_status(api_status_short: str) -> MatchStatus` — `"NS"` → `SCHEDULED`, `"FT"` → `FINISHED`, etc.
- `_record_from_api(fixture_dict: dict) -> FixtureRecord` — produces a normalised dataclass.
- `_upsert_fixtures(session, records: list[FixtureRecord], competition_id: UUID) -> SyncResult` — diff against DB, INSERT/UPDATE.

**Returns** `SyncResult`:

```python
@dataclass
class SyncResult:
    created: int
    updated: int
    unchanged: int
    api_only_count: int                  # in API but already in DB (info)
    db_only_count: int                   # in DB but not in API (warning, not deleted)
    changed_fields: dict[str, int]       # e.g. {"kickoff": 3, "home_team": 16}
    unmatched_flag_teams: list[str]      # teams whose name doesn't match flags.ts keys
```

### `scripts/seed_fixtures.py`

Argparse CLI wrapper. Resolves the competition (creates if missing), calls one of `sync_from_api` / `sync_from_cache`, prints `SyncResult` summary.

**CLI:**

```bash
docker-compose exec backend python -m scripts.seed_fixtures
  [--from-cache]            # skip API call, use existing JSON
  [--no-cache-write]        # call API but don't update cache
  [--cache-path PATH]       # default: backend/data/wc2026_fixtures.json
  [--league N]              # default: 1
  [--season YYYY]           # default: 2026
  [--competition-name STR]  # default: "FIFA World Cup 2026"
```

Default behaviour: fetch from API, write to cache, upsert into DB. Safely re-runnable.

## Data flow

### Default flow

```
[CLI] → [football_api.get_fixtures(1, 2026)]
     → [write JSON to backend/data/wc2026_fixtures.json]
     → [fixture_sync._parse + _upsert]
     → [print SyncResult]
```

### Offline / re-seed from cache (`--from-cache`)

```
[CLI] → [read backend/data/wc2026_fixtures.json]
     → [fixture_sync._parse + _upsert]
     → [print SyncResult]
```

### First-run cleanup (one-off, performed manually before first seed)

```sql
-- Run via: docker-compose exec backend psql ...  OR  ad-hoc inside an exec session
DELETE FROM scores;
DELETE FROM match_predictions;
DELETE FROM team_predictions;
DELETE FROM fixtures;
-- competitions and users untouched
```

This is **not** committed as a script. It is a one-time bootstrap step we run by hand and then never again.

## API integration details

### Endpoints used

| Endpoint | Purpose | Calls per run |
|----------|---------|---------------|
| `GET /status` | Smoke test (already done; not invoked by seed) | 0 |
| `GET /fixtures?league=1&season=2026` | All 104 fixtures | 1 |
| `GET /teams?league=1&season=2026` | Team list, used for group inference + flag check | 1 |

Two API calls per fetch run; well under the 100/day Free tier budget.

### Response shape (relevant fields)

```json
{
  "response": [
    {
      "fixture": {
        "id": 1234567,
        "date": "2026-06-11T20:00:00+00:00",
        "status": {"short": "NS", "long": "Not Started"},
        "venue": {"name": "AT&T Stadium", "city": "Arlington"}
      },
      "league": {
        "id": 1, "season": 2026,
        "round": "Group Stage - 1"
      },
      "teams": {
        "home": {"id": 99,  "name": "United States"},
        "away": {"id": 100, "name": "Mexico"}
      }
    }
  ]
}
```

For unresolved knockouts, `teams.home.name` may be `null` or a slot identifier (e.g. `"Group A Winner"`). The exact behaviour for WC2026 will be **verified during implementation** with a single live API call. The parser handles both cases by using a synthesised placeholder if the name is missing.

### Field mapping (API → `Fixture`)

| Fixture column | Source | Notes |
|----------------|--------|-------|
| `external_id` | `str(fixture.id)` | Stable identity for upsert |
| `home_team` | `teams.home.name` or synthesised slot string | See "Placeholder names" |
| `away_team` | `teams.away.name` or synthesised slot string | See "Placeholder names" |
| `kickoff` | parsed `fixture.date` → UTC datetime | API returns UTC |
| `stage` | derived from `league.round` | See "Round parser" |
| `group` | derived from `/teams` response group field | See "Group inference" |
| `match_number` | 1-indexed sequence per stage, sorted by `kickoff` ascending | e.g. group: 1-72, round_of_32: 1-16, round_of_16: 1-8, ..., final: 1 |
| `status` | mapped from `fixture.status.short` | See "Status mapping" |
| `competition_id` | resolved from `--competition-name` | Set by CLI |

### Round parser (`_parse_round`)

| Input | `(stage, group_letter)` |
|-------|--------------------------|
| `"Group Stage - 1"` | `("group", None)` (group inferred separately) |
| `"Group Stage - 2"` | `("group", None)` |
| `"Group Stage - 3"` | `("group", None)` |
| `"Round of 32"` | `("round_of_32", None)` |
| `"Round of 16"` | `("round_of_16", None)` |
| `"Quarter-finals"` | `("quarter_final", None)` |
| `"Semi-finals"` | `("semi_final", None)` |
| `"3rd Place Final"` | `("third_place", None)` |
| `"Final"` | `("final", None)` |
| anything else | raises `UnknownRoundError(round_str)` |

Failing loudly on unknowns is intentional. Silent fallthrough at seed time would mis-stage fixtures and corrupt scoring; better to halt and inspect.

### Status mapping (`_parse_status`)

| API `status.short` | `MatchStatus` |
|--------------------|----------------|
| `NS`, `TBD` | `SCHEDULED` |
| `1H`, `2H`, `ET`, `BT`, `P`, `LIVE` | `LIVE` |
| `HT` | `HALFTIME` |
| `FT`, `AET`, `PEN` | `FINISHED` |
| `PST`, `SUSP`, `INT` | `POSTPONED` |
| `CANC`, `ABD`, `AWD`, `WO` | `CANCELLED` |
| anything else | `SCHEDULED` (with warning log) |

### Group inference

Group letter (`A`–`L`) is not reliably present in `league.round`. Two-step approach:

1. Call `GET /teams?league=1&season=2026` to retrieve all 48 teams.
2. Group field on each team's record is parsed (api-sports.io includes group info on the team object for tournament leagues; **exact field name verified during implementation**).
3. Build `team_name → group_letter` map.
4. When parsing each group-stage fixture, look up `home_team` in the map and assign that group letter.

If the API doesn't expose group information directly, fall back to a hand-maintained mapping in the cache JSON's top-level `meta.groups` block (still committed to git, still auditable):

```json
{
  "meta": {
    "fetched_at": "2026-05-02T15:00:00Z",
    "league": 1,
    "season": 2026,
    "groups": {
      "United States": "A",
      "Mexico": "I",
      "...": "..."
    }
  },
  "response": [ ... ]
}
```

The presence/absence of `meta.groups` is checked by `_record_from_api` and used as the group source if API team objects don't carry the field. Decision is made once during implementation step 6 and the design accommodates either outcome without a code change beyond the parser's group-source resolution.

### Placeholder names for unresolved knockouts

When `teams.home.name` (or `teams.away.name`) is `null`:

- Try the slot identifier from API if present (api-sports.io sometimes provides this in `teams.home.name` as `"Winner Group A"` or similar).
- Otherwise synthesise: `f"slot:{stage}:{external_id}:{home_or_away}"` — guaranteed unique, easy to spot in the UI as unresolved, will be overwritten by live-scoring sync once the API resolves it.

### New stage value: `"third_place"`

Adds a new recognised value to `Fixture.stage` (the field is a free-form string, no enum constraint, so no migration needed). Frontend bracket display does **not** need to render the third-place match; it's seeded for completeness only. Whether to expose it in the predictor UI is a separate decision deferred by the user.

### Schema migration impact

**None.** `Fixture.stage` is a string column with no DB-level constraint, so adding `"third_place"` is a data change, not a schema change. No Alembic migration required.

## DB operations

Single transaction, in this order:

```python
existing = {f.external_id: f for f in await load_fixtures(session, competition_id)}
records = parse(api_response)

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
- API team-name resolution (`"slot:..."` → `"USA"`) → 1 updated; same path used by live-scoring
- API removes a fixture → **DB row preserved**, warning logged. Pruning is intentionally not implemented (a future `--prune` flag could be added if ever needed).

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

Expected output: `~72 / ~95 / ~220 / ~88` rows deleted respectively. After this, the seed script runs against an empty fixtures table and inserts all 104.

## Edge cases and error handling

| Scenario | Behaviour |
|----------|-----------|
| HTTP 401/403 (bad/missing key) | Raise `FootballAPIAuthError` with helpful message |
| HTTP 429 | Retry once after `Retry-After`; then raise `FootballAPIRateLimitError` |
| Network timeout | 3 retries with backoff (1s, 4s, 9s) |
| `response: []` (zero fixtures) | Raise `FootballAPIEmptyResponseError` (likely wrong league/season) |
| `--from-cache` and file missing | Raise `FileNotFoundError` with path |
| Unknown `league.round` value | Raise `UnknownRoundError` — abort entire run |
| Team name not in `flags.ts` | Log warning, include in `SyncResult.unmatched_flag_teams`, do not fail |
| Malformed JSON in cache | Raise `ValueError` from JSON parser |
| Mid-seed exception | Transaction rollback, DB unchanged |

### Flag-name mismatch handling

After upsert, the script extracts unique team names from the seeded fixtures and cross-references them against keys in `frontend/src/lib/utils/flags.ts`. Teams whose names don't appear in the keys list are printed as a warning summary at the end of the run:

```
Warning: 3 team names not present in frontend flags.ts:
  - "United States" (use "USA"? both already mapped — OK)
  - "Korea Republic" (consider adding alias)
  - "IR Iran" (consider adding alias for "Iran")
```

The warning does not fail the run. Resolving mismatches is a follow-up frontend task; flags simply don't render until aliases are added.

## Testing

`backend/tests/test_fixture_sync.py`:

- `test_parse_round_group_stage_matchday_1`
- `test_parse_round_round_of_32`
- `test_parse_round_round_of_16`
- `test_parse_round_quarter_finals`
- `test_parse_round_semi_finals`
- `test_parse_round_third_place`
- `test_parse_round_final`
- `test_parse_round_unknown_raises`
- `test_parse_status_all_known_codes`
- `test_parse_status_unknown_falls_back_to_scheduled`
- `test_upsert_inserts_new_fixtures` — empty DB + 8 records → 8 created
- `test_upsert_updates_kickoff_change` — 1 existing, kickoff differs → 1 updated
- `test_upsert_updates_team_resolution` — `"slot:..."` → `"USA"` triggers update; predictions on the fixture remain
- `test_upsert_skips_unchanged` — same input twice → 0 changes
- `test_upsert_db_only_logs_warning` — DB has fixture not in API → not deleted, warning recorded
- `test_sync_from_cache_reads_json` — happy path
- `test_unmatched_flag_teams_collected` — team name not in flags.ts list → recorded in result

**Test fixture:** `backend/tests/fixtures/wc2026_sample.json` — 8 hand-crafted fixtures covering: 2 group stage (with real teams), 2 R32 (with placeholder slot names), 1 R16, 1 quarter-final, 1 third-place, 1 final.

**Skipped tests (intentional):**

- `football_api.py` HTTP client unit tests — thin wrapper, integration-tested by the first real seed run
- Full integration test against the live API — costs daily quota, one-off sanity check during implementation suffices

## Out of scope

- Live-scoring sync (Phase 4 work). `fixture_sync.sync_from_api` is the integration point; Phase 4 wires up a scheduler.
- Auto-resolution of placeholder team strings in our DB (handled by live-scoring sync mirroring API state once groups complete).
- Score data ingestion (the `scores` table, score pushed back to fixtures, etc.) — Phase 4.
- Frontend `flags.ts` updates for newly-introduced team-name aliases — follow-up task once the warning list is reviewed.
- Adding a `competition_id` FK to `team_predictions` — long-term schema cleanup, not blocking.
- A `--prune` flag for deleting DB-only fixtures — explicitly deferred; not needed for v1.
- Paid API-Football tier upgrade for live-scoring throughput — deferred to Phase 4 setup.

## Future considerations

- **`--prune` flag** for cases where FIFA actually removes a fixture (rare, never expected). Would require explicit confirmation given the destructive cascade.
- **`competition_id` FK on `team_predictions`** — would let `team_predictions` deletion be scoped per-competition, useful if you ever run a second tournament alongside WC2026.
- **Paid API-Football tier** — Free tier (100 calls/day) covers seeding indefinitely. Live-scoring during match days needs ~$10–20/mo plan.
- **Venue and broadcast metadata** — API returns venue + city; not used by current schema. Could be added to `Fixture` if useful for match cards.

## Implementation checklist (for the plan)

1. Create `app/services/external/__init__.py` and `football_api.py` with the HTTP client + domain exceptions.
2. Create `app/services/fixture_sync.py` with parser, upsert, `SyncResult`, and `sync_from_api` / `sync_from_cache` entry points.
3. Create `backend/data/` directory; ensure `wc2026_fixtures.json` is committed once generated.
4. Create `scripts/seed_fixtures.py` CLI wrapper.
5. Add `backend/tests/fixtures/wc2026_sample.json` and `test_fixture_sync.py`.
6. Verify: real API call to confirm response shape (round strings, group exposure, placeholder behaviour). Adjust parser if needed.
7. Run first-run cleanup SQL (manual one-off).
8. Run `python -m scripts.seed_fixtures` and inspect `SyncResult`.
9. Spot-check 3 fixtures in the DB by hand against fifa.com / Wikipedia.
10. Commit `wc2026_fixtures.json` to git as the auditable seed snapshot.

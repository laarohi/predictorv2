"""Probe Football-Data.org to lock down the response shape for the WC2026 fixtures seed.

One-off discovery tool: hits /v4/competitions/WC, /matches and /teams,
saves raw JSON to backend/data/probe/, and prints structured analysis of
the fields we depend on (stage enum values, group enum values, status,
team name placeholder shape, venue presence, rate limit headers).

Run with:
    docker-compose exec backend python -m scripts.probe_football_data

Costs ~3 API calls on the free tier (10/min limit).
"""

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from app.config import get_settings


def _show_rate_limits(resp: httpx.Response, label: str) -> None:
    avail = resp.headers.get("X-RequestsAvailable-Minute") or resp.headers.get(
        "X-RequestsAvailable"
    )
    reset = resp.headers.get("X-RequestCounter-Reset")
    print(f"  [{label}] HTTP {resp.status_code}, avail={avail}, reset_in={reset}s")


async def main() -> None:
    settings = get_settings()
    if not settings.football_data_token:
        print("ERROR: FOOTBALL_DATA_TOKEN not set in container env.", file=sys.stderr)
        print("  Run: docker-compose run --rm backend ... (uses .env at run time)", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(__file__).parent.parent / "data" / "probe"
    out_dir.mkdir(parents=True, exist_ok=True)

    headers = {"X-Auth-Token": settings.football_data_token}
    base = settings.football_data_base_url

    async with httpx.AsyncClient(timeout=15.0) as client:
        print("Calls:")
        # 1. Competition info — confirms current season
        rc = await client.get(f"{base}/competitions/WC", headers=headers)
        _show_rate_limits(rc, "competition")
        comp_payload = rc.json() if rc.status_code == 200 else {"error": rc.text, "status": rc.status_code}
        (out_dir / "fd_competition.json").write_text(json.dumps(comp_payload, indent=2))

        # 2. Matches — all of them
        rm = await client.get(f"{base}/competitions/WC/matches", headers=headers)
        _show_rate_limits(rm, "matches   ")
        matches_payload = rm.json() if rm.status_code == 200 else {"error": rm.text, "status": rm.status_code}
        (out_dir / "fd_matches.json").write_text(json.dumps(matches_payload, indent=2))

        # 3. Teams
        rt = await client.get(f"{base}/competitions/WC/teams", headers=headers)
        _show_rate_limits(rt, "teams     ")
        teams_payload = rt.json() if rt.status_code == 200 else {"error": rt.text, "status": rt.status_code}
        (out_dir / "fd_teams.json").write_text(json.dumps(teams_payload, indent=2))

    print()
    print("=" * 60)
    print("COMPETITION")
    print("=" * 60)
    if "error" in comp_payload:
        print("Error:", comp_payload)
    else:
        print(f"name={comp_payload.get('name')!r}")
        print(f"code={comp_payload.get('code')!r}")
        cs = comp_payload.get("currentSeason") or {}
        print(f"currentSeason: id={cs.get('id')} startDate={cs.get('startDate')} "
              f"endDate={cs.get('endDate')} matchday={cs.get('currentMatchday')}")

    print()
    print("=" * 60)
    print("MATCHES ANALYSIS")
    print("=" * 60)
    if "error" in matches_payload:
        print("Error:", matches_payload)
        return

    matches = matches_payload.get("matches", [])
    print(f"Total matches: {len(matches)}")
    print(f"Resultset count: {matches_payload.get('resultSet', {})}")

    if not matches:
        print("(no matches returned — coverage gap or season not yet populated)")
        return

    # Stage values
    stages = Counter(m.get("stage") for m in matches)
    print(f"\nDistinct stage values ({len(stages)}):")
    for s, c in sorted(stages.items(), key=lambda x: -x[1]):
        print(f"  {c:>3}× {s!r}")

    # Group values
    groups = Counter(m.get("group") for m in matches)
    print(f"\nDistinct group values ({len(groups)}):")
    for g, c in sorted(groups.items(), key=lambda x: (x[0] is None, str(x[0]))):
        print(f"  {c:>3}× {g!r}")

    # Status values
    statuses = Counter(m.get("status") for m in matches)
    print(f"\nDistinct status values ({len(statuses)}):")
    for s, c in sorted(statuses.items()):
        print(f"  {c:>3}× {s!r}")

    # Team representations for knockouts (look for placeholder vs real names)
    print("\nKnockout team representations (sample of up to 6):")
    shown = 0
    for m in matches:
        if m.get("stage") in {"LAST_16", "LAST_32", "QUARTER_FINALS", "SEMI_FINALS", "FINAL"} and shown < 6:
            ht, at = m.get("homeTeam") or {}, m.get("awayTeam") or {}
            print(
                f"  stage={m.get('stage'):<14} "
                f"home={(ht.get('name'),  ht.get('id'))!s:<40} "
                f"away={(at.get('name'),  at.get('id'))!s}"
            )
            shown += 1

    # Field shape
    print("\nMatch object keys (top-level):", list(matches[0].keys()))
    if matches[0].get("homeTeam"):
        print("homeTeam keys:", list(matches[0]["homeTeam"].keys()))

    # Venue presence
    venues = sum(1 for m in matches if m.get("venue"))
    print(f"\nMatches with venue: {venues}/{len(matches)}")

    # Sample matches
    sample_g = next((m for m in matches if m.get("stage") == "GROUP_STAGE"), None)
    sample_k = next((m for m in matches if m.get("stage") and m.get("stage") != "GROUP_STAGE"), None)
    if sample_g:
        print("\nSample GROUP_STAGE match:")
        print(json.dumps(sample_g, indent=2))
    if sample_k:
        print("\nSample knockout match:")
        print(json.dumps(sample_k, indent=2))

    print()
    print("=" * 60)
    print("TEAMS ANALYSIS")
    print("=" * 60)
    if "error" in teams_payload:
        print("Error:", teams_payload)
    else:
        teams = teams_payload.get("teams", [])
        print(f"Total teams: {len(teams)}")
        if teams:
            print("Team object keys:", list(teams[0].keys()))
            print("\nSample team:")
            print(json.dumps(teams[0], indent=2))

    print()
    print("Raw responses saved under backend/data/probe/:")
    print("  fd_competition.json")
    print("  fd_matches.json")
    print("  fd_teams.json")


if __name__ == "__main__":
    asyncio.run(main())

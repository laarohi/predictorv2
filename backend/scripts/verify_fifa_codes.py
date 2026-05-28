"""
Compare our DB team names + frontend FIFA codes against the official FIFA API.

Produces a table:
  DB Name | DB Code (teamCodes.ts) | FIFA Name | FIFA Code | Match?

Usage:
  docker compose exec backend python scripts/verify_fifa_codes.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import async_session_maker  # noqa: E402
from app.services.fifa_codes import TEAM_NAME_TO_FIFA_CODE as DB_TEAM_TO_CODE  # noqa: E402


def fetch_fifa_rankings() -> dict[str, dict]:
    """Fetch all rankings from the official FIFA API, keyed by country code."""
    resp = httpx.get(
        "https://api.fifa.com/api/v3/rankings/",
        params={"gender": 1, "count": 300},
        headers={"User-Agent": "PredictorV2/1.0"},
        timeout=15.0,
    )
    resp.raise_for_status()
    results = resp.json()["Results"]
    by_code: dict[str, dict] = {}
    for r in results:
        code = r["IdCountry"]
        name = r["TeamName"][0]["Description"] if r["TeamName"] else "?"
        by_code[code] = {
            "name": name,
            "code": code,
            "rank": r["Rank"],
            "points": r["DecimalTotalPoints"],
        }
    return by_code


async def get_db_teams() -> list[str]:
    """Get distinct team names from fixtures (excluding slot: placeholders)."""
    async with async_session_maker() as session:
        result = await session.execute(
            text(
                "SELECT DISTINCT t FROM ("
                "  SELECT home_team AS t FROM fixtures "
                "  UNION "
                "  SELECT away_team AS t FROM fixtures"
                ") sub "
                "WHERE t NOT LIKE 'slot:%' "
                "ORDER BY t"
            )
        )
        return [row[0] for row in result.fetchall()]


async def main():
    print("Fetching FIFA rankings from api.fifa.com ...")
    fifa = fetch_fifa_rankings()
    print(f"  Got {len(fifa)} ranked teams.\n")

    print("Fetching DB team names ...")
    db_teams = await get_db_teams()
    print(f"  Got {len(db_teams)} teams in fixtures.\n")

    hdr = f"{'DB Name':<25} {'DB Code':<10} {'FIFA Name':<25} {'FIFA Code':<10} {'Match?':<8} {'Rank'}"
    sep = "-" * len(hdr)
    print(sep)
    print(hdr)
    print(sep)

    mismatches = []
    missing_code = []
    missing_fifa = []

    for team in db_teams:
        db_code = DB_TEAM_TO_CODE.get(team)
        if not db_code:
            missing_code.append(team)
            print(f"{team:<25} {'???':<10} {'—':<25} {'—':<10} {'NO MAP':<8}")
            continue

        fifa_entry = fifa.get(db_code)
        if not fifa_entry:
            missing_fifa.append((team, db_code))
            print(f"{team:<25} {db_code:<10} {'NOT FOUND':<25} {'—':<10} {'MISS':<8}")
            continue

        match = "✓" if db_code == fifa_entry["code"] else "✗"
        if match == "✗":
            mismatches.append((team, db_code, fifa_entry))

        print(
            f"{team:<25} {db_code:<10} "
            f"{fifa_entry['name']:<25} {fifa_entry['code']:<10} "
            f"{match:<8} #{fifa_entry['rank']}"
        )

    print(sep)
    print(f"\nSummary: {len(db_teams)} DB teams, "
          f"{len(db_teams) - len(missing_code) - len(missing_fifa) - len(mismatches)} matched, "
          f"{len(mismatches)} code mismatches, "
          f"{len(missing_code)} unmapped, "
          f"{len(missing_fifa)} not in FIFA rankings")

    if mismatches:
        print("\n⚠ Code mismatches:")
        for team, db_code, fe in mismatches:
            print(f"  {team}: DB={db_code}, FIFA={fe['code']}")

    if missing_code:
        print(f"\n⚠ DB teams not in our code map: {missing_code}")

    if missing_fifa:
        print(f"\n⚠ DB codes not found in FIFA rankings: {missing_fifa}")


if __name__ == "__main__":
    asyncio.run(main())

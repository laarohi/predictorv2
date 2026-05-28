"""Fetch the latest FIFA men's world ranking and replace the local snapshot.

Calls the public FIFA API at ``api.fifa.com/api/v3/rankings/``, then
truncates and refills the ``fifa_rankings`` table.  The API returns the
full 211-team list in one request, so a wholesale replace is simpler and
safer than an upsert.

Usage:
    docker compose exec backend python scripts/sync_fifa_rankings.py
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.database import async_session_maker  # noqa: E402
from app.models.fifa_ranking import FifaRanking  # noqa: E402

FIFA_API_URL = "https://api.fifa.com/api/v3/rankings/"


def fetch_fifa_rankings() -> list[dict]:
    """GET the FIFA API. Returns the raw Results list (211 entries)."""
    resp = httpx.get(
        FIFA_API_URL,
        params={"gender": 1, "count": 300},
        headers={"User-Agent": "PredictorV2/1.0"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()["Results"]


def _team_name(entry: dict) -> str:
    """Pick the English description; fall back to the first locale."""
    names = entry.get("TeamName") or []
    for n in names:
        if n.get("Locale", "").startswith("en"):
            return n["Description"]
    return names[0]["Description"] if names else "?"


async def sync_rankings(results: list[dict]) -> tuple[int, int]:
    """Truncate + insert. Returns (deleted_count, inserted_count)."""
    async with async_session_maker() as session:
        deleted = (await session.execute(delete(FifaRanking))).rowcount

        for r in results:
            session.add(
                FifaRanking(
                    rank=r["Rank"],
                    country_code=r["IdCountry"],
                    team_name=_team_name(r),
                    points=float(r["DecimalTotalPoints"]),
                    pub_date=datetime.fromisoformat(r["PubDate"]),
                )
            )
        await session.commit()
        return deleted or 0, len(results)


async def main() -> None:
    print(f"Fetching {FIFA_API_URL} ...")
    results = fetch_fifa_rankings()
    pub_date = results[0]["PubDate"] if results else "?"
    print(f"  Got {len(results)} teams, published {pub_date}")

    deleted, inserted = await sync_rankings(results)
    print(f"Sync complete: deleted {deleted} stale rows, inserted {inserted} fresh rows")


if __name__ == "__main__":
    asyncio.run(main())

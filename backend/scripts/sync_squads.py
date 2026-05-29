"""Scrape 2026 World Cup squads from Wikipedia into the ``players`` table.

Parses the *wikitext source* of
https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads (via the MediaWiki
API) rather than the rendered HTML — every player is a regular
``{{nat fs g player|...}}`` template whose named params never reorder, which
makes the parse far more stable than HTML scraping.

For each player we pull four fields the award bonus dropdowns need:
  - full_name  ← ``name=[[Kylian Mbappé]]``           (accented display name)
  - surname / first_name ← ``sortname=Mbappe, Kylian`` (ASCII, accent-stripped)
  - position   ← ``pos=FW``
  - date_of_birth ← the BIRTH y/m/d args of the ``{{birth date and age2}}``
                    sub-template in ``age=``

Country comes from the enclosing ``===Heading===`` section, mapped to our
canonical DB team name (e.g. "Czech Republic" → "Czechia") so player rows
line up with fixtures, flags, and fifa_codes.

The table is rebuilt wholesale (truncate + refill), mirroring
sync_fifa_rankings.py: squads are still firming up, so a clean replace is
simpler and self-healing. Re-run as final 26-man lists land.

Usage:
    docker compose exec backend python scripts/sync_squads.py
"""

import asyncio
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.database import async_session_maker  # noqa: E402
from app.models.player import Player  # noqa: E402
from app.services.fifa_codes import TEAM_NAME_TO_FIFA_CODE  # noqa: E402

WIKI_API = "https://en.wikipedia.org/w/api.php"
PAGE = "2026 FIFA World Cup squads"

# Wikipedia section headings → our canonical DB team name (the fifa_codes key).
# Only the spellings that differ need an entry; everything else maps to itself.
HEADING_ALIASES = {
    "Czech Republic": "Czechia",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Cape Verde": "Cape Verde Islands",
    "DR Congo": "Congo DR",
}

# A level-3 section heading: ===Country=== (not ==Group== or =Coaches=).
HEADING_RE = re.compile(r"^===\s*([^=].*?)\s*===\s*$")
PLAYER_LINE = "nat fs g player"
NAME_RE = re.compile(r"\|\s*name\s*=\s*\[\[([^\]]+?)\]\]")
POS_RE = re.compile(r"\|\s*pos\s*=\s*([A-Za-z]{2})")
SORT_RE = re.compile(r"\|\s*sortname\s*=\s*([^|{}]+)")
# {{birth date and age2|REF_y|REF_m|REF_d|BIRTH_y|BIRTH_m|BIRTH_d}} — birth is last 3.
DOB2_RE = re.compile(
    r"birth date and age2\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*\d+\s*"
    r"\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})",
    re.I,
)
# {{birth date and age|BIRTH_y|BIRTH_m|BIRTH_d|...}} — birth is first 3.
DOB1_RE = re.compile(
    r"birth date and age\s*\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})", re.I
)


def fetch_wikitext() -> str:
    """GET the squads page wikitext from the MediaWiki API."""
    resp = httpx.get(
        WIKI_API,
        params={
            "action": "parse",
            "page": PAGE,
            "prop": "wikitext",
            "format": "json",
            "redirects": 1,
        },
        headers={"User-Agent": "PredictorV2/1.0 (squad sync)"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["parse"]["wikitext"]["*"]


def _display_name(raw: str) -> str:
    """[[Article|Display]] → Display ; [[Name]] → Name."""
    return raw.split("|")[-1].strip()


def _parse_dob(line: str) -> date | None:
    m = DOB2_RE.search(line) or DOB1_RE.search(line)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_players(wikitext: str) -> tuple[list[dict], list[str]]:
    """Walk the wikitext, returning (player dicts, unmapped-country warnings)."""
    players: list[dict] = []
    unmapped: set[str] = set()
    country: str | None = None
    code: str | None = None

    for raw_line in wikitext.split("\n"):
        line = raw_line.strip()
        heading = HEADING_RE.match(line)
        if heading:
            wiki_name = heading.group(1)
            country = HEADING_ALIASES.get(wiki_name, wiki_name)
            code = TEAM_NAME_TO_FIFA_CODE.get(country)
            continue

        if PLAYER_LINE not in line or country is None:
            continue

        name_m = NAME_RE.search(line)
        pos_m = POS_RE.search(line)
        sort_m = SORT_RE.search(line)
        if not (name_m and pos_m):
            continue  # malformed row — skip rather than store junk

        # Split "Surname, First" from sortname; fall back to last-token split.
        surname = first_name = ""
        if sort_m:
            parts = sort_m.group(1).strip().split(",", 1)
            surname = parts[0].strip()
            first_name = parts[1].strip() if len(parts) > 1 else ""
        else:
            toks = _display_name(name_m.group(1)).rsplit(" ", 1)
            surname = toks[-1]
            first_name = toks[0] if len(toks) > 1 else ""

        if code is None:
            unmapped.add(country)

        players.append(
            {
                "full_name": _display_name(name_m.group(1)),
                "surname": surname,
                "first_name": first_name,
                "country": country,
                "country_code": code,
                "position": pos_m.group(1).upper(),
                "date_of_birth": _parse_dob(line),
            }
        )

    return players, sorted(unmapped)


async def sync_players(rows: list[dict]) -> tuple[int, int]:
    """Truncate + insert. Returns (deleted_count, inserted_count)."""
    async with async_session_maker() as session:
        deleted = (await session.execute(delete(Player))).rowcount
        for r in rows:
            session.add(Player(**r))
        await session.commit()
        return deleted or 0, len(rows)


async def main() -> None:
    print(f"Fetching '{PAGE}' wikitext ...")
    wikitext = fetch_wikitext()
    rows, unmapped = parse_players(wikitext)

    teams = sorted({r["country"] for r in rows})
    print(f"  Parsed {len(rows)} players across {len(teams)} teams")
    if unmapped:
        print(f"  WARNING: no FIFA code for: {', '.join(unmapped)} "
              "(rows still inserted with country_code=NULL)")

    deleted, inserted = await sync_players(rows)
    print(f"Sync complete: deleted {deleted} stale rows, inserted {inserted} fresh rows")


if __name__ == "__main__":
    asyncio.run(main())

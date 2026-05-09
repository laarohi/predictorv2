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


async def _resolve_competition(session: AsyncSession, name: str, external_id: str) -> Competition:
    """Find or create a competition. Backfills external_id if missing on existing row."""
    result = await session.execute(select(Competition).where(Competition.name == name))
    comp = result.scalar_one_or_none()
    if comp is not None:
        if comp.external_id != external_id:
            comp.external_id = external_id
            await session.commit()
            await session.refresh(comp)
        return comp
    comp = Competition(name=name, external_id=external_id)
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
        comp = await _resolve_competition(session, args.competition_name, args.competition_code)

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

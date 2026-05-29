"""Seed pre-tournament UX phase test data.

Flips the active competition into the "pre_tournament" UX phase so the
landing dashboard renders `DashboardPre`. Idempotent — run any time, the
goal is the end state, not the diff.

End state:
  - phase1_deadline = now + 7 days  (so phase1_locked = False)
  - is_phase2_active = False
  - All scores deleted
  - All group fixtures reset to SCHEDULED

Run with: docker-compose exec backend python -m scripts.seed_phase_pretournament
Undo with: docker-compose exec backend python -m scripts.seed_phase_pretournament --undo
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus


DATABASE_URL = "postgresql+asyncpg://predictor:predictor@db:5432/predictor"


async def seed_pretournament() -> None:
    """Set up pre-tournament test state."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(Competition).where(Competition.is_active == True)  # noqa: E712
        )
        competition = result.scalar_one_or_none()
        if not competition:
            print("No active competition found. Run seed_fixtures.py first.")
            return

        print(f"Found competition: {competition.name}")

        # Clear scores
        await session.execute(text("DELETE FROM scores"))
        print("Deleted all scores")

        # Delete any knockout fixtures (they were seeded by phase2 test)
        result = await session.execute(
            select(Fixture).where(
                Fixture.competition_id == competition.id,
                Fixture.stage != "group",
            )
        )
        knockout_fixtures = result.scalars().all()
        for fixture in knockout_fixtures:
            await session.delete(fixture)
        if knockout_fixtures:
            print(f"Deleted {len(knockout_fixtures)} knockout fixtures")

        # Reset group fixtures
        result = await session.execute(
            select(Fixture).where(
                Fixture.competition_id == competition.id,
                Fixture.stage == "group",
            )
        )
        group_fixtures = result.scalars().all()
        for fixture in group_fixtures:
            fixture.status = MatchStatus.SCHEDULED
        print(f"Reset {len(group_fixtures)} group fixtures to scheduled")

        # Phase 1 deadline: 7 days from now (so phase1_locked = False)
        competition.phase1_deadline = datetime.now(timezone.utc) + timedelta(days=7)
        # Phase 2 inactive
        competition.is_phase2_active = False
        competition.phase2_activated_at = None
        competition.phase2_bracket_deadline = None
        competition.phase2_deadline = None
        print("Set phase1_deadline = now + 7d; cleared phase 2 state")

        await session.commit()
        print("\nPre-tournament UX phase seeded successfully.")
        print("Visit / to see DashboardPre (or /?uxPhase=pre_tournament to force).")


async def undo_pretournament() -> None:
    """Undo: simply clear phase1_deadline."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(Competition).where(Competition.is_active == True)  # noqa: E712
        )
        competition = result.scalar_one_or_none()
        if not competition:
            print("No active competition found.")
            return

        competition.phase1_deadline = None
        await session.commit()
        print("Cleared phase1_deadline. Pre-tournament seed undone.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--undo":
        asyncio.run(undo_pretournament())
    else:
        asyncio.run(seed_pretournament())

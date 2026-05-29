"""Seed between-phases UX state test data.

Flips the active competition into the "between_phases" UX phase so the
landing dashboard renders `DashboardBetween`. Reuses `seed_phase2_test.py`
logic (finished group stage + knockout fixtures), then explicitly sets
the Phase 2 bracket deadline 24h in the future so the bracket is still
open (phase2_bracket_locked = False).

End state:
  - phase1_deadline in the past (phase1_locked = True)
  - All group fixtures FINISHED with scores
  - is_phase2_active = True, phase2_bracket_deadline = now + 24h
  - Knockout fixtures created but SCHEDULED

Run with: docker-compose exec backend python -m scripts.seed_phase_between
Undo with: docker-compose exec backend python -m scripts.seed_phase_between --undo
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.seed_phase2_test import (  # noqa: E402
    seed_phase2_test,
    undo_phase2_test,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from app.models.competition import Competition  # noqa: E402


DATABASE_URL = "postgresql+asyncpg://predictor:predictor@db:5432/predictor"


async def set_between_deadlines() -> None:
    """Override deadlines after seed_phase2_test runs."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(Competition).where(Competition.is_active == True)  # noqa: E712
        )
        competition = result.scalar_one_or_none()
        if not competition:
            return

        now = datetime.now(timezone.utc)
        # Phase 1 deadline in the past (so phase1_locked = True regardless of
        # whatever seed_phase2_test left it as).
        competition.phase1_deadline = now - timedelta(days=14)
        # Phase 2 bracket deadline 24h ahead → between_phases UX phase
        competition.phase2_bracket_deadline = now + timedelta(hours=24)
        await session.commit()
        print(
            "Set phase1_deadline = -14d, phase2_bracket_deadline = +24h "
            "→ between_phases UX phase."
        )


async def main_seed() -> None:
    await seed_phase2_test()
    await set_between_deadlines()
    print("\nBetween-phases UX phase seeded successfully.")
    print("Visit / to see DashboardBetween (or /?uxPhase=between_phases to force).")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--undo":
        asyncio.run(undo_phase2_test())
    else:
        asyncio.run(main_seed())

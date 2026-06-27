"""DEV-ONLY: finish the group stage + activate Phase 2 for local testing.

This is a TEST harness for exercising the Phase 2 entry flow against the
realistic dev DB. It:
  1. Adds deterministic scores to every still-SCHEDULED group fixture and
     marks it FINISHED, so actual group standings are complete (the Phase 2
     bracket seeds its R32 from these standings).
  2. Activates Phase 2 with a bracket_deadline 15 min before the first
     scheduled knockout kickoff.

It does NOT touch knockout fixtures — the knockout_resolver populates those.
Reverse any time by restoring the snapshot in .dev-db-snapshots/.

    docker exec predictor-backend python -m scripts.dev_phase2_activate
    docker exec predictor-backend python -m scripts.dev_phase2_activate --undo

NEVER run against the prod ('predictor') docker context.
"""

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from app.models._datetime import aware_utc, utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource

DB_URL = "postgresql+asyncpg://predictor:predictor@db:5432/predictor"


def _deterministic_score(match_number: int | None, idx: int) -> tuple[int, int]:
    """Varied-but-deterministic scoreline so standings aren't all ties."""
    seed = (match_number or idx) + 1
    return seed % 4, (seed * 2) % 3


async def _run() -> None:
    engine = create_async_engine(DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        comp = (
            await session.execute(select(Competition).where(Competition.is_active == True))  # noqa: E712
        ).scalar_one_or_none()
        if not comp:
            print("No active competition found.")
            return

        # 1. Finish every still-scheduled group fixture.
        scheduled_groups = (
            await session.execute(
                select(Fixture).where(
                    Fixture.competition_id == comp.id,
                    Fixture.stage == "group",
                    Fixture.status != MatchStatus.FINISHED,
                )
            )
        ).scalars().all()
        added = 0
        for i, fx in enumerate(scheduled_groups):
            existing = (
                await session.execute(select(Score).where(Score.fixture_id == fx.id))
            ).scalar_one_or_none()
            if existing is None:
                h, a = _deterministic_score(fx.match_number, i)
                session.add(
                    Score(
                        fixture_id=fx.id,
                        home_score=h,
                        away_score=a,
                        source=ScoreSource.MANUAL,
                        verified=True,
                    )
                )
            fx.status = MatchStatus.FINISHED
            added += 1
        print(f"Finished {added} group fixtures (now all groups complete).")

        # 2. Activate Phase 2 with a deadline 15 min before the first KO kickoff.
        first_ko = (
            await session.execute(
                select(func.min(Fixture.kickoff)).where(
                    Fixture.competition_id == comp.id,
                    Fixture.stage != "group",
                )
            )
        ).scalar_one_or_none()
        if first_ko is None:
            print("No knockout fixtures found — cannot set a bracket deadline.")
            return
        first_ko = aware_utc(first_ko)
        deadline = first_ko - timedelta(minutes=15)
        comp.is_phase2_active = True
        comp.phase2_activated_at = utc_now()
        comp.phase2_bracket_deadline = deadline
        comp.updated_at = utc_now()
        await session.commit()
        print(f"Phase 2 ACTIVE. First KO kickoff {first_ko.isoformat()}; "
              f"bracket_deadline {deadline.isoformat()}.")


async def _undo() -> None:
    engine = create_async_engine(DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        comp = (
            await session.execute(select(Competition).where(Competition.is_active == True))  # noqa: E712
        ).scalar_one_or_none()
        if comp:
            comp.is_phase2_active = False
            comp.phase2_activated_at = None
            comp.phase2_bracket_deadline = None
            await session.commit()
        print("Phase 2 deactivated. (Group scores left intact — restore a snapshot "
              "for a full reset.)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--undo":
        asyncio.run(_undo())
    else:
        asyncio.run(_run())

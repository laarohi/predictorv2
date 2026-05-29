"""Seed post-competition UX phase test data.

Flips the active competition into the "post_competition" UX phase by
marking the FINAL fixture as FINISHED with a score. deriveUxPhase
detects the finished final and returns 'post_competition' regardless of
lock state.

End state (additive on top of any other seed):
  - The single fixture with stage == "final" has status = FINISHED
  - A Score row exists for that fixture

If no final fixture exists yet (e.g. seed_phase2_test hasn't been run with
later knockout rounds), this script just reports it and exits gracefully —
the layout follow-up plan will introduce a fuller knockout fixture set.

Run with: docker-compose exec backend python -m scripts.seed_phase_post
Undo with: docker-compose exec backend python -m scripts.seed_phase_post --undo
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource


DATABASE_URL = "postgresql+asyncpg://predictor:predictor@db:5432/predictor"

# A safely fictitious final score. The retrospective dashboard doesn't
# care about the specifics — only that the final fixture is finished.
FINAL_HOME_SCORE = 2
FINAL_AWAY_SCORE = 1


async def seed_post() -> None:
    """Mark the final as finished."""
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

        # Find the final fixture
        result = await session.execute(
            select(Fixture).where(
                Fixture.competition_id == competition.id,
                Fixture.stage == "final",
            )
        )
        final = result.scalar_one_or_none()
        if not final:
            print(
                "No final fixture found. Run seed_phase2_test (or a later seed "
                "with the full knockout bracket) before seeding post-competition."
            )
            return

        # Existing score? Skip.
        existing = await session.execute(
            select(Score).where(Score.fixture_id == final.id)
        )
        if not existing.scalar_one_or_none():
            score = Score(
                fixture_id=final.id,
                home_score=FINAL_HOME_SCORE,
                away_score=FINAL_AWAY_SCORE,
                source=ScoreSource.MANUAL,
                verified=True,
            )
            session.add(score)
            print(
                f"Added score {FINAL_HOME_SCORE}-{FINAL_AWAY_SCORE} for the final."
            )
        else:
            print("Final already has a score; leaving it.")

        final.status = MatchStatus.FINISHED
        print(f"Marked final ({final.home_team} vs {final.away_team}) as FINISHED.")

        await session.commit()
        print("\nPost-competition UX phase seeded successfully.")
        print("Visit / to see DashboardPost (or /?uxPhase=post_competition to force).")


async def undo_post() -> None:
    """Revert the final to SCHEDULED and remove its score."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(Competition).where(Competition.is_active == True)  # noqa: E712
        )
        competition = result.scalar_one_or_none()
        if not competition:
            return

        result = await session.execute(
            select(Fixture).where(
                Fixture.competition_id == competition.id,
                Fixture.stage == "final",
            )
        )
        final = result.scalar_one_or_none()
        if not final:
            print("No final fixture to undo.")
            return

        result = await session.execute(
            select(Score).where(Score.fixture_id == final.id)
        )
        score = result.scalar_one_or_none()
        if score:
            await session.delete(score)
            print("Deleted score for the final.")

        final.status = MatchStatus.SCHEDULED
        print("Reverted final to SCHEDULED.")

        await session.commit()
        print("Post-competition seed undone.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--undo":
        asyncio.run(undo_post())
    else:
        asyncio.run(seed_post())

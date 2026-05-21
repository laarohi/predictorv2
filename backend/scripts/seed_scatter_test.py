"""Seed scatter plot test data.

Creates 20 test users with predictions for the US vs Mexico Group A fixture,
covering all visual states: exact scores, correct outcomes, wrong predictions,
draws on the diagonal, and count-grouped dots.

Run with: docker-compose exec backend python -m scripts.seed_scatter_test
Undo with: docker-compose exec backend python -m scripts.seed_scatter_test --undo
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bcrypt import gensalt, hashpw
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score, ScoreSource
from app.models.user import User

# Identifier for cleanup
TEST_EMAIL_DOMAIN = "@predictor.test"

# Actual result: US 2-1 Mexico (home win)
ACTUAL_HOME = 2
ACTUAL_AWAY = 1

# 20 predictions with realistic distribution
# (home_score, away_score) — see plan for expected visual outcomes
PREDICTIONS = [
    # Exact: 2-1 x2 → green star with count=2
    (2, 1),
    (2, 1),
    # Correct outcome (home win): 1-0 x4 → large yellow circle
    (1, 0),
    (1, 0),
    (1, 0),
    (1, 0),
    # Correct outcome: 3-1 x2 → medium yellow circle
    (3, 1),
    (3, 1),
    # Correct outcome: 2-0 x2 → medium yellow circle
    (2, 0),
    (2, 0),
    # Correct outcome: 3-0 x1 → small yellow circle
    (3, 0),
    # Wrong (draw zone): 1-1 x3 → medium red on diagonal
    (1, 1),
    (1, 1),
    (1, 1),
    # Wrong (draw zone): 0-0 x1 → small red in corner
    (0, 0),
    # Wrong (away win): 0-1 x2 → medium red
    (0, 1),
    (0, 1),
    # Wrong (away win): 1-2 x2 → medium red
    (1, 2),
    (1, 2),
    # Wrong (away win): 0-2 x1 → small red in corner
    (0, 2),
]


async def seed_scatter_test():
    """Create 20 test users + predictions for US vs Mexico."""
    engine = create_async_engine(
        "postgresql+asyncpg://predictor:predictor@db:5432/predictor",
        echo=False,
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get active competition
        result = await session.execute(
            select(Competition).where(Competition.is_active == True)
        )
        competition = result.scalar_one_or_none()
        if not competition:
            print("No active competition found. Run seed_data.py first.")
            return

        print(f"Found competition: {competition.name}")

        # Find the US vs Mexico fixture (Group A)
        result = await session.execute(
            select(Fixture).where(
                Fixture.competition_id == competition.id,
                Fixture.home_team == "United States",
                Fixture.away_team == "Mexico",
                Fixture.group == "A",
            )
        )
        fixture = result.scalar_one_or_none()
        if not fixture:
            print("US vs Mexico Group A fixture not found. Check seed_data.py.")
            return

        print(f"Found fixture: {fixture.home_team} vs {fixture.away_team} (match #{fixture.match_number})")

        # Mark fixture as FINISHED
        fixture.status = MatchStatus.FINISHED

        # Add score (2-1) if not already present
        result = await session.execute(
            select(Score).where(Score.fixture_id == fixture.id)
        )
        existing_score = result.scalar_one_or_none()
        if not existing_score:
            score = Score(
                fixture_id=fixture.id,
                home_score=ACTUAL_HOME,
                away_score=ACTUAL_AWAY,
                source=ScoreSource.MANUAL,
                verified=True,
            )
            session.add(score)
            print(f"Added score: {ACTUAL_HOME}-{ACTUAL_AWAY}")
        else:
            print(f"Score already exists: {existing_score.home_score}-{existing_score.away_score}")

        # Create 20 test users and their predictions
        password_hash = hashpw("testpass123".encode("utf-8"), gensalt()).decode("utf-8")
        users_created = 0
        predictions_created = 0

        for i, (home_score, away_score) in enumerate(PREDICTIONS, start=1):
            email = f"testuser{i}{TEST_EMAIL_DOMAIN}"

            # Check if user already exists
            result = await session.execute(
                select(User).where(User.email == email)
            )
            user = result.scalar_one_or_none()

            if not user:
                user = User(
                    email=email,
                    name=f"Test Player {i}",
                    password_hash=password_hash,
                    competition_id=competition.id,
                    is_active=True,
                )
                session.add(user)
                await session.flush()  # get user.id
                users_created += 1

            # Check if prediction already exists
            result = await session.execute(
                select(MatchPrediction).where(
                    MatchPrediction.user_id == user.id,
                    MatchPrediction.fixture_id == fixture.id,
                )
            )
            existing_pred = result.scalar_one_or_none()

            if not existing_pred:
                prediction = MatchPrediction(
                    user_id=user.id,
                    fixture_id=fixture.id,
                    home_score=home_score,
                    away_score=away_score,
                    phase=PredictionPhase.PHASE_1,
                    locked_at=datetime.utcnow(),
                )
                session.add(prediction)
                predictions_created += 1

        await session.commit()

        print(f"\nCreated {users_created} test users")
        print(f"Created {predictions_created} predictions")
        print(f"Fixture status: {fixture.status}")
        print("\nScatter plot test data seeded successfully!")
        print("Open the results page and expand the US vs Mexico match.")

    await engine.dispose()


async def undo_scatter_test():
    """Remove all test users, their predictions, and the fixture score."""
    engine = create_async_engine(
        "postgresql+asyncpg://predictor:predictor@db:5432/predictor",
        echo=False,
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get active competition
        result = await session.execute(
            select(Competition).where(Competition.is_active == True)
        )
        competition = result.scalar_one_or_none()
        if not competition:
            print("No active competition found.")
            return

        # Find test users
        result = await session.execute(
            select(User).where(User.email.endswith(TEST_EMAIL_DOMAIN))
        )
        test_users = result.scalars().all()

        # Delete their predictions
        predictions_deleted = 0
        for user in test_users:
            result = await session.execute(
                select(MatchPrediction).where(MatchPrediction.user_id == user.id)
            )
            preds = result.scalars().all()
            for pred in preds:
                await session.delete(pred)
                predictions_deleted += 1

        # Delete test users
        for user in test_users:
            await session.delete(user)
        print(f"Deleted {len(test_users)} test users")
        print(f"Deleted {predictions_deleted} predictions")

        # Remove score from US vs Mexico fixture and reset status
        result = await session.execute(
            select(Fixture).where(
                Fixture.competition_id == competition.id,
                Fixture.home_team == "United States",
                Fixture.away_team == "Mexico",
                Fixture.group == "A",
            )
        )
        fixture = result.scalar_one_or_none()
        if fixture:
            result = await session.execute(
                select(Score).where(Score.fixture_id == fixture.id)
            )
            score = result.scalar_one_or_none()
            if score:
                await session.delete(score)
                print("Deleted fixture score")
            fixture.status = MatchStatus.SCHEDULED
            print("Reset fixture to SCHEDULED")

        await session.commit()
        print("\nScatter plot test data removed successfully!")

    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--undo":
        asyncio.run(undo_scatter_test())
    else:
        asyncio.run(seed_scatter_test())

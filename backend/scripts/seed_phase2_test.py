"""Seed Phase 2 test data.

This script:
1. Marks group stage fixtures as FINISHED
2. Adds scores to create standings
3. Activates Phase 2
4. Adds knockout fixtures with actual team names

Run with: docker-compose exec backend python -m scripts.seed_phase2_test
Undo with: docker-compose exec backend python -m scripts.seed_phase2_test --undo
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource


# Predetermined group stage results (to create clear standings)
# Format: (home_score, away_score) for each match in order
GROUP_RESULTS = {
    "A": [(2, 1), (1, 0), (3, 0), (2, 2), (1, 1), (0, 2)],  # USA 1st, Mexico 2nd, Jamaica 3rd
    "B": [(3, 2), (1, 1), (2, 0), (1, 0), (2, 1), (0, 1)],  # Brazil 1st, Argentina 2nd, Colombia 3rd
    "C": [(1, 1), (2, 0), (2, 1), (1, 0), (3, 0), (1, 2)],  # England 1st, France 2nd, Germany 3rd
    "D": [(2, 0), (1, 1), (1, 0), (2, 1), (0, 0), (3, 1)],  # Portugal 1st, Netherlands 2nd, Belgium 3rd
    "E": [(1, 0), (2, 1), (1, 1), (0, 0), (2, 0), (1, 0)],  # Italy 1st, Croatia 2nd, Switzerland 3rd
    "F": [(2, 1), (1, 0), (3, 1), (2, 0), (1, 1), (0, 1)],  # Japan 1st, South Korea 2nd, Australia 3rd
    "G": [(1, 0), (2, 2), (2, 0), (1, 1), (1, 0), (2, 1)],  # Morocco 1st, Senegal 2nd, Nigeria 3rd
    "H": [(2, 0), (1, 1), (1, 0), (3, 1), (0, 0), (2, 0)],  # Canada 1st, Ecuador 2nd, Peru 3rd
    "I": [(1, 0), (2, 1), (0, 0), (1, 2), (2, 1), (1, 0)],  # Poland 1st, Ukraine 2nd, Sweden 3rd
    "J": [(2, 1), (1, 0), (1, 1), (2, 0), (0, 1), (2, 2)],  # Serbia 1st, Turkey 2nd, Scotland 3rd
    "K": [(1, 0), (2, 1), (1, 1), (0, 0), (2, 0), (1, 0)],  # Iran 1st, Qatar 2nd, UAE 3rd
    "L": [(1, 0), (2, 0), (1, 1), (0, 1), (2, 1), (0, 0)],  # Tunisia 1st, Cameroon 2nd, Ghana 3rd
}

# Round of 32 knockout fixtures (based on expected standings above)
# Using simplified bracket: 1A vs 2B, 1B vs 2A, etc.
KNOCKOUT_FIXTURES = [
    # Round of 32
    ("round_of_32", "United States", "Argentina", 49),
    ("round_of_32", "Brazil", "Mexico", 50),
    ("round_of_32", "England", "Netherlands", 51),
    ("round_of_32", "Portugal", "France", 52),
    ("round_of_32", "Italy", "South Korea", 53),
    ("round_of_32", "Japan", "Croatia", 54),
    ("round_of_32", "Morocco", "Ecuador", 55),
    ("round_of_32", "Canada", "Senegal", 56),
    ("round_of_32", "Poland", "Turkey", 57),
    ("round_of_32", "Serbia", "Ukraine", 58),
    ("round_of_32", "Iran", "Cameroon", 59),
    ("round_of_32", "Tunisia", "Qatar", 60),
    # Third place qualifiers
    ("round_of_32", "Germany", "Colombia", 61),  # 3C vs 3B
    ("round_of_32", "Belgium", "Switzerland", 62),  # 3D vs 3E
    ("round_of_32", "Australia", "Nigeria", 63),  # 3F vs 3G
    ("round_of_32", "Peru", "Sweden", 64),  # 3H vs 3I
]


async def seed_phase2_test():
    """Set up Phase 2 test data."""
    engine = create_async_engine(
        "postgresql+asyncpg://predictor:predictor@db:5432/predictor",
        echo=False,
    )

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

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

        # Get all group stage fixtures
        result = await session.execute(
            select(Fixture)
            .where(
                Fixture.competition_id == competition.id,
                Fixture.stage == "group",
            )
            .order_by(Fixture.group, Fixture.match_number)
        )
        group_fixtures = result.scalars().all()

        if not group_fixtures:
            print("No group fixtures found. Run seed_data.py first.")
            return

        print(f"Found {len(group_fixtures)} group stage fixtures")

        # Group fixtures by group for result assignment
        fixtures_by_group: dict[str, list[Fixture]] = {}
        for fixture in group_fixtures:
            group = fixture.group
            if group not in fixtures_by_group:
                fixtures_by_group[group] = []
            fixtures_by_group[group].append(fixture)

        # Add scores and mark as finished
        scores_added = 0
        for group, fixtures in fixtures_by_group.items():
            results = GROUP_RESULTS.get(group, [])
            # Sort fixtures by match_number to ensure correct order
            fixtures.sort(key=lambda f: f.match_number or 0)

            for i, fixture in enumerate(fixtures):
                if i < len(results):
                    home_score, away_score = results[i]

                    # Check if score already exists
                    existing = await session.execute(
                        select(Score).where(Score.fixture_id == fixture.id)
                    )
                    if existing.scalar_one_or_none():
                        continue

                    # Create score
                    score = Score(
                        fixture_id=fixture.id,
                        home_score=home_score,
                        away_score=away_score,
                        source=ScoreSource.MANUAL,
                        verified=True,
                    )
                    session.add(score)

                    # Mark fixture as finished
                    fixture.status = MatchStatus.FINISHED
                    scores_added += 1

        print(f"Added {scores_added} scores to group fixtures")

        # Activate Phase 2
        competition.is_phase2_active = True
        competition.phase2_activated_at = datetime.now(timezone.utc)
        competition.phase2_bracket_deadline = datetime.now(timezone.utc) + timedelta(days=7)
        print("Activated Phase 2")

        # Add knockout fixtures
        knockout_start = datetime.now(timezone.utc) + timedelta(days=1)
        fixtures_added = 0

        for stage, home_team, away_team, match_number in KNOCKOUT_FIXTURES:
            # Check if fixture already exists
            existing = await session.execute(
                select(Fixture).where(
                    Fixture.competition_id == competition.id,
                    Fixture.match_number == match_number,
                    Fixture.stage == stage,
                )
            )
            if existing.scalar_one_or_none():
                continue

            fixture = Fixture(
                competition_id=competition.id,
                home_team=home_team,
                away_team=away_team,
                kickoff=knockout_start + timedelta(hours=fixtures_added * 3),
                stage=stage,
                group=None,
                match_number=match_number,
                status=MatchStatus.SCHEDULED,
            )
            session.add(fixture)
            fixtures_added += 1

        print(f"Added {fixtures_added} knockout fixtures")

        await session.commit()
        print("\nPhase 2 test data seeded successfully!")
        print("You can now test the Phase 2 UI in the frontend.")


async def undo_phase2_test():
    """Undo Phase 2 test data."""
    engine = create_async_engine(
        "postgresql+asyncpg://predictor:predictor@db:5432/predictor",
        echo=False,
    )

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        # Get active competition
        result = await session.execute(
            select(Competition).where(Competition.is_active == True)
        )
        competition = result.scalar_one_or_none()

        if not competition:
            print("No active competition found.")
            return

        # Delete all scores
        await session.execute("DELETE FROM scores")
        print("Deleted all scores")

        # Delete knockout fixtures
        result = await session.execute(
            select(Fixture).where(
                Fixture.competition_id == competition.id,
                Fixture.stage != "group",
            )
        )
        knockout_fixtures = result.scalars().all()
        for fixture in knockout_fixtures:
            await session.delete(fixture)
        print(f"Deleted {len(knockout_fixtures)} knockout fixtures")

        # Reset group fixtures to scheduled
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

        # Deactivate Phase 2
        competition.is_phase2_active = False
        competition.phase2_activated_at = None
        competition.phase2_bracket_deadline = None
        print("Deactivated Phase 2")

        await session.commit()
        print("\nPhase 2 test data removed successfully!")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--undo":
        asyncio.run(undo_phase2_test())
    else:
        asyncio.run(seed_phase2_test())

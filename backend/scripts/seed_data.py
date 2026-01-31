"""Seed data script for testing.

Run with: docker-compose exec backend python -m scripts.seed_data
"""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus


# Sample teams for World Cup 2026 (using likely qualifiers)
GROUPS = {
    "A": ["United States", "Mexico", "Jamaica", "Costa Rica"],
    "B": ["Brazil", "Argentina", "Colombia", "Chile"],
    "C": ["England", "France", "Germany", "Spain"],
    "D": ["Portugal", "Netherlands", "Belgium", "Denmark"],
    "E": ["Italy", "Croatia", "Switzerland", "Austria"],
    "F": ["Japan", "South Korea", "Australia", "Saudi Arabia"],
    "G": ["Morocco", "Senegal", "Nigeria", "Egypt"],
    "H": ["Canada", "Ecuador", "Peru", "Venezuela"],
    "I": ["Poland", "Ukraine", "Sweden", "Czech Republic"],
    "J": ["Serbia", "Turkey", "Scotland", "Norway"],
    "K": ["Iran", "Qatar", "UAE", "Iraq"],
    "L": ["Tunisia", "Cameroon", "Ghana", "Ivory Coast"],
}

# Tournament start date (actual WC2026 starts June 11, 2026)
TOURNAMENT_START = datetime(2026, 6, 11, 18, 0, 0)


def generate_group_fixtures(
    competition_id: uuid.UUID,
    group: str,
    teams: list[str],
    start_date: datetime,
) -> list[Fixture]:
    """Generate round-robin fixtures for a group."""
    fixtures = []
    match_number = 1

    # Each team plays 3 matches in round-robin
    matchups = [
        (0, 1, 0),  # Team 0 vs Team 1, day offset 0
        (2, 3, 0),  # Team 2 vs Team 3, day offset 0
        (0, 2, 4),  # Team 0 vs Team 2, day offset 4
        (1, 3, 4),  # Team 1 vs Team 3, day offset 4
        (0, 3, 8),  # Team 0 vs Team 3, day offset 8
        (1, 2, 8),  # Team 1 vs Team 2, day offset 8
    ]

    for home_idx, away_idx, day_offset in matchups:
        kickoff = start_date + timedelta(days=day_offset, hours=(match_number % 3) * 3)
        fixtures.append(
            Fixture(
                competition_id=competition_id,
                home_team=teams[home_idx],
                away_team=teams[away_idx],
                kickoff=kickoff,
                stage="group",
                group=group,
                match_number=match_number,
                status=MatchStatus.SCHEDULED,
            )
        )
        match_number += 1

    return fixtures


async def seed_database():
    """Seed the database with test data."""
    # Create async engine
    engine = create_async_engine(
        "postgresql+asyncpg://predictor:predictor@db:5432/predictor",
        echo=True,
    )

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        # Create competition
        competition = Competition(
            name="FIFA World Cup 2026",
            description="The 23rd FIFA World Cup, hosted by United States, Canada, and Mexico",
            entry_fee=Decimal("20.00"),
            phase1_deadline=TOURNAMENT_START - timedelta(hours=24),
            phase2_deadline=TOURNAMENT_START + timedelta(days=14),
            config_file="config/worldcup2026.yml",
            is_active=True,
        )
        session.add(competition)
        await session.flush()

        print(f"Created competition: {competition.name} (ID: {competition.id})")

        # Generate fixtures for all groups
        all_fixtures = []
        group_start_offsets = {
            "A": 0, "B": 0, "C": 1, "D": 1,
            "E": 2, "F": 2, "G": 3, "H": 3,
            "I": 4, "J": 4, "K": 5, "L": 5,
        }

        for group, teams in GROUPS.items():
            day_offset = group_start_offsets[group]
            group_start = TOURNAMENT_START + timedelta(days=day_offset)
            fixtures = generate_group_fixtures(competition.id, group, teams, group_start)
            all_fixtures.extend(fixtures)

        session.add_all(all_fixtures)
        await session.commit()

        print(f"Created {len(all_fixtures)} group stage fixtures")

        # Summary by group
        for group in sorted(GROUPS.keys()):
            group_fixtures = [f for f in all_fixtures if f.group == group]
            print(f"  Group {group}: {len(group_fixtures)} matches - {GROUPS[group]}")


async def clear_database():
    """Clear all data from the database."""
    engine = create_async_engine(
        "postgresql+asyncpg://predictor:predictor@db:5432/predictor",
        echo=True,
    )

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        # Delete in order due to foreign keys
        await session.execute("DELETE FROM match_predictions")
        await session.execute("DELETE FROM team_predictions")
        await session.execute("DELETE FROM scores")
        await session.execute("DELETE FROM fixtures")
        await session.execute("DELETE FROM users")
        await session.execute("DELETE FROM competitions")
        await session.commit()
        print("Database cleared")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--clear":
        asyncio.run(clear_database())
    else:
        asyncio.run(seed_database())

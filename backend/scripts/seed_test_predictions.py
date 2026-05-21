"""Seed group-stage predictions for the 20 Test Player N users.

Populates one Phase 1 prediction per (test_player, group_fixture) so the
rarity-bonus projection on the Results page has enough per-fixture
predictors to produce a meaningful agreement distribution.

Per fixture we pick a deterministic "favored" outcome (seeded from the
fixture id so reruns are reproducible) and weighted-sample the 20 test
players across {favored, contender, draw} so most lean toward the
favorite but some agreement bands fall in the rare-pick zone.

Run:    docker-compose exec backend python -m scripts.seed_test_predictions
Undo:   docker-compose exec backend python -m scripts.seed_test_predictions --undo
"""

import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.user import User

TEST_EMAIL_PREFIX = "testuser"
TEST_EMAIL_DOMAIN = "@predictor.test"

# Score variations per outcome bucket. Probabilities don't need to be exact —
# the distribution just needs to look like real human picks (more 1-0 / 2-1
# than 5-4).
HOME_SCORES: list[tuple[int, int]] = [
    (1, 0), (1, 0), (1, 0),
    (2, 0), (2, 0),
    (2, 1), (2, 1),
    (3, 1),
    (3, 0),
]
DRAW_SCORES: list[tuple[int, int]] = [
    (0, 0), (0, 0),
    (1, 1), (1, 1), (1, 1),
    (2, 2),
]
AWAY_SCORES: list[tuple[int, int]] = [
    (0, 1), (0, 1), (0, 1),
    (0, 2), (0, 2),
    (1, 2), (1, 2),
    (1, 3),
    (0, 3),
]

# How the 20 test players split across outcomes for a given fixture. The
# favored outcome gets the lion's share, then contender, then draw. We
# rotate which outcome is "favored" deterministically per fixture so the
# 1/X/2 distribution across fixtures isn't lopsided.
SPLIT_WEIGHTS = (12, 5, 3)  # favored / contender / draw  (sums to 20)


def predictions_for_fixture(fixture_id: str, n_players: int = 20) -> list[tuple[int, int]]:
    """Return n_players (home_score, away_score) tuples with a realistic
    spread for one fixture. Deterministic in fixture_id so reruns produce
    identical seed data."""
    rng = random.Random(fixture_id)
    # Choose favored outcome — biased toward "1" (home advantage), like
    # real-world predictor distributions, but rotated by fixture so groups
    # don't all look identical.
    favored = rng.choices(["1", "2", "X"], weights=[5, 3, 2], k=1)[0]
    if favored == "1":
        contender = "2"
    elif favored == "2":
        contender = "1"
    else:
        # Draw is favored — rare; contender is whichever side rng picks
        contender = rng.choice(["1", "2"])
    other = ({"1", "X", "2"} - {favored, contender}).pop()

    buckets_by_outcome = {
        "1": HOME_SCORES,
        "X": DRAW_SCORES,
        "2": AWAY_SCORES,
    }

    n_fav, n_con, n_oth = SPLIT_WEIGHTS
    assignments: list[str] = [favored] * n_fav + [contender] * n_con + [other] * n_oth
    assignments = assignments[:n_players]
    rng.shuffle(assignments)
    return [rng.choice(buckets_by_outcome[o]) for o in assignments]


async def seed_test_predictions() -> None:
    engine = create_async_engine(
        "postgresql+asyncpg://predictor:predictor@db:5432/predictor", echo=False
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        competition = (
            await session.execute(select(Competition).where(Competition.is_active == True))
        ).scalar_one_or_none()
        if not competition:
            print("No active competition.")
            return

        # Get the 20 test players in order
        users: list[User] = []
        for i in range(1, 21):
            email = f"{TEST_EMAIL_PREFIX}{i}{TEST_EMAIL_DOMAIN}"
            u = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if u is None:
                print(f"Missing user: {email} — run seed_scatter_test first.")
                return
            users.append(u)
        print(f"Found {len(users)} test players.")

        # Group-stage fixtures only — knockout brackets are predicted via the
        # bracket UI, not per-match in Phase 1.
        fixtures = (
            (
                await session.execute(
                    select(Fixture)
                    .where(
                        Fixture.competition_id == competition.id,
                        Fixture.stage == "group",
                    )
                    .order_by(Fixture.match_number)
                )
            )
            .scalars()
            .all()
        )
        print(f"Seeding {len(users)} predictions across {len(fixtures)} group fixtures.")

        created = 0
        skipped = 0
        now = utc_now()
        for fx in fixtures:
            preds = predictions_for_fixture(str(fx.id), n_players=len(users))
            for user, (home_score, away_score) in zip(users, preds):
                existing = (
                    await session.execute(
                        select(MatchPrediction).where(
                            MatchPrediction.user_id == user.id,
                            MatchPrediction.fixture_id == fx.id,
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    skipped += 1
                    continue
                session.add(
                    MatchPrediction(
                        user_id=user.id,
                        fixture_id=fx.id,
                        home_score=home_score,
                        away_score=away_score,
                        phase=PredictionPhase.PHASE_1,
                        locked_at=now,
                    )
                )
                created += 1
        await session.commit()
        print(f"Created {created} predictions, skipped {skipped} (already existed).")

    await engine.dispose()


async def undo_test_predictions() -> None:
    """Delete every MatchPrediction owned by a Test Player N user."""
    engine = create_async_engine(
        "postgresql+asyncpg://predictor:predictor@db:5432/predictor", echo=False
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        users = (
            (
                await session.execute(
                    select(User).where(User.email.like(f"{TEST_EMAIL_PREFIX}%{TEST_EMAIL_DOMAIN}"))
                )
            )
            .scalars()
            .all()
        )
        ids = [u.id for u in users]
        if not ids:
            print("No test players found.")
            return
        preds = (
            (
                await session.execute(
                    select(MatchPrediction).where(MatchPrediction.user_id.in_(ids))
                )
            )
            .scalars()
            .all()
        )
        for p in preds:
            await session.delete(p)
        await session.commit()
        print(f"Deleted {len(preds)} predictions from {len(ids)} test players.")

    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--undo":
        asyncio.run(undo_test_predictions())
    else:
        asyncio.run(seed_test_predictions())

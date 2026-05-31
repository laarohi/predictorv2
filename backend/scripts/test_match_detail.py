"""Temporary test fixture setup for the /results/[fixture_id] page.

Picks two real Group A fixtures and force-locks them by shifting their
kickoffs into the recent past. One of them also gets a Score so the
post-match design renders; the other stays locked-but-unscored so the
pre-match design renders.

Run:    docker-compose exec backend python -m scripts.test_match_detail
Undo:   docker-compose exec backend python -m scripts.test_match_detail --undo

The original kickoffs / statuses are written to
`scripts/.test_match_detail_state.json` so `--undo` is exact.
"""

import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import delete, select

from app.models._datetime import utc_now
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource

# ----- Test config ---------------------------------------------------------

# Mexico vs South Africa — gets a finished score (post-match design)
FINISHED_ID = "12a499c3-914d-4e2f-a62b-1bce44815ad6"
FINISHED_HOME_GOALS = 2
FINISHED_AWAY_GOALS = 1

# South Korea vs Czechia — stays locked, no score (pre-match design)
LOCKED_ID = "e46454e1-6c18-4df1-a887-2bb1086b1d05"

STATE_FILE = Path(__file__).parent / ".test_match_detail_state.json"

# Hard-coded async URL — mirrors seed_scatter_test.py. The container's
# DATABASE_URL env points at the sync driver (psycopg2), which doesn't work
# with create_async_engine.
DB_URL = "postgresql+asyncpg://predictor:predictor@db:5432/predictor"


# ----- Helpers -------------------------------------------------------------

async def _get_session() -> AsyncSession:
    engine = create_async_engine(DB_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return Session()


async def _load_fixture(session: AsyncSession, fixture_id: str) -> Fixture:
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fx = result.scalar_one_or_none()
    if not fx:
        raise SystemExit(f"Fixture {fixture_id} not found")
    return fx


# ----- Apply ---------------------------------------------------------------

async def apply():
    if STATE_FILE.exists():
        print(
            f"State file already exists at {STATE_FILE}. Run --undo first, or "
            f"delete the file manually if you know the DB is already clean."
        )
        return

    session = await _get_session()
    async with session.begin():
        finished = await _load_fixture(session, FINISHED_ID)
        locked = await _load_fixture(session, LOCKED_ID)

        # Save originals so --undo is exact.
        state = {
            "finished": {
                "id": str(finished.id),
                "kickoff": finished.kickoff.isoformat(),
                "status": finished.status.value,
            },
            "locked": {
                "id": str(locked.id),
                "kickoff": locked.kickoff.isoformat(),
                "status": locked.status.value,
            },
        }
        STATE_FILE.write_text(json.dumps(state, indent=2))

        now = utc_now()

        # FINISHED: shift kickoff 2h into the past, mark finished, add Score
        finished.kickoff = now - timedelta(hours=2)
        finished.status = MatchStatus.FINISHED
        finished.minute = None
        session.add(finished)

        # Replace any existing Score row (shouldn't exist but be safe)
        await session.execute(delete(Score).where(Score.fixture_id == finished.id))
        score = Score(
            fixture_id=finished.id,
            home_score=FINISHED_HOME_GOALS,
            away_score=FINISHED_AWAY_GOALS,
            source=ScoreSource.MANUAL,
            verified=True,
        )
        session.add(score)

        # LOCKED: shift kickoff to 3 minutes from now so is_locked() returns
        # true (within the 5-minute window) but status stays scheduled.
        locked.kickoff = now + timedelta(minutes=3)
        locked.status = MatchStatus.SCHEDULED
        session.add(locked)

    await session.close()
    print(
        f"Applied.\n"
        f"  FINISHED  {finished.home_team} vs {finished.away_team}  "
        f"({FINISHED_HOME_GOALS}-{FINISHED_AWAY_GOALS})\n"
        f"            /results/{FINISHED_ID}\n"
        f"  LOCKED    {locked.home_team} vs {locked.away_team}  (pre-match)\n"
        f"            /results/{LOCKED_ID}\n"
        f"\nState saved to {STATE_FILE} — run with --undo to restore."
    )


# ----- Undo ----------------------------------------------------------------

async def undo():
    if not STATE_FILE.exists():
        print(f"No state file at {STATE_FILE} — nothing to undo.")
        return

    state = json.loads(STATE_FILE.read_text())
    session = await _get_session()
    async with session.begin():
        for key in ("finished", "locked"):
            row = state[key]
            fx = await _load_fixture(session, row["id"])
            fx.kickoff = _parse_iso(row["kickoff"])
            fx.status = MatchStatus(row["status"])
            fx.minute = None
            session.add(fx)
            if key == "finished":
                await session.execute(delete(Score).where(Score.fixture_id == fx.id))

    await session.close()
    STATE_FILE.unlink()
    print("Undone. Kickoffs + statuses restored, score row removed.")


def _parse_iso(s: str):
    from datetime import datetime

    return datetime.fromisoformat(s)


# ----- CLI -----------------------------------------------------------------

async def main():
    if "--undo" in sys.argv:
        await undo()
    else:
        await apply()


if __name__ == "__main__":
    import os

    # This script shifts real fixture kickoffs into the past (to force locks) —
    # destructive if ever run against production data. Refuse unless explicitly
    # in a dev environment.
    if os.environ.get("DEBUG", "").lower() not in ("1", "true", "yes") and "--force" not in sys.argv:
        print(
            "Refusing to run: shifts real fixture kickoffs and is dev-only. "
            "Set DEBUG=true (or pass --force) to run it intentionally."
        )
        raise SystemExit(2)
    asyncio.run(main())

"""Read-only dump of Phase 1 predictions for the bracket-misalignment audit.

Companion to ``frontend/src/lib/utils/bracketAudit.test.ts``: that harness
re-runs the exact UI bracket-resolution pipeline over this dump to find
users whose saved knockout picks no longer fit the bracket implied by
their (since-edited) group score predictions.

Emits one JSON document on stdout: group fixtures, FIFA rankings, and
per-user Phase 1 match predictions + raw bracket (team_predictions) rows.
Strictly read-only — no writes, no migrations.

Run against PROD without deploying (the script is piped via stdin, so it
doesn't need to exist inside the container):

    ssh pred-mplex 'cd ~/predictorv2 && docker compose exec -T backend python -' \
        < backend/scripts/audit_bracket_dump.py > /tmp/bracket_dump_prod.json

Or against the local dev stack:

    docker-compose exec -T backend python - \
        < backend/scripts/audit_bracket_dump.py > /tmp/bracket_dump_dev.json

Then analyse:

    cd frontend && BRACKET_AUDIT_DUMP=/tmp/bracket_dump_prod.json npx vitest run bracketAudit
"""

import asyncio
import json
import sys

# When run as a file from scripts/, make the app package importable.
# When piped via `python -` inside the container, cwd is already /app
# and __file__ is undefined.
if "__file__" in globals():
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import select  # noqa: E402

from app.database import async_session_maker  # noqa: E402
from app.models.fixture import Fixture  # noqa: E402
from app.models.prediction import (  # noqa: E402
    MatchPrediction,
    PredictionPhase,
    TeamPrediction,
)
from app.models.user import User  # noqa: E402
from app.services.standings import _resolve_fifa_rankings  # noqa: E402


async def main() -> None:
    async with async_session_maker() as session:
        fixtures = (
            (await session.execute(select(Fixture).where(Fixture.stage == "group")))
            .scalars()
            .all()
        )
        rankings = await _resolve_fifa_rankings(session)
        users = (await session.execute(select(User))).scalars().all()
        match_preds = (
            (
                await session.execute(
                    select(MatchPrediction).where(
                        MatchPrediction.phase == PredictionPhase.PHASE_1
                    )
                )
            )
            .scalars()
            .all()
        )
        team_preds = (
            (
                await session.execute(
                    select(TeamPrediction).where(
                        TeamPrediction.phase == PredictionPhase.PHASE_1
                    )
                )
            )
            .scalars()
            .all()
        )

    group_fixture_ids = {f.id for f in fixtures}

    mp_by_user: dict = {}
    for p in match_preds:
        if p.fixture_id not in group_fixture_ids:
            continue
        mp_by_user.setdefault(p.user_id, []).append(
            {
                "fixture_id": str(p.fixture_id),
                "home_score": p.home_score,
                "away_score": p.away_score,
            }
        )

    tp_by_user: dict = {}
    for t in team_preds:
        tp_by_user.setdefault(t.user_id, []).append({"team": t.team, "stage": t.stage})

    out = {
        "fifa_rankings": rankings,
        "fixtures": [
            {
                "id": str(f.id),
                "group": f.group,
                "home_team": f.home_team,
                "away_team": f.away_team,
            }
            for f in fixtures
        ],
        "users": [
            {
                "id": str(u.id),
                "name": u.name,
                "email": u.email,
                "match_predictions": mp_by_user.get(u.id, []),
                "bracket": tp_by_user.get(u.id, []),
            }
            for u in users
        ],
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    asyncio.run(main())

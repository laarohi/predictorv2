"""DEV-ONLY: seed test@example.com with a rich knockout snapshot so the
DwScoringJourney grouped bars + DwKnockoutMatchScores strip show real colour.

Produces an honest mid-R32 state:
  * finishes 6 more R32 fixtures (on top of the existing Canada–S.Korea),
  * gives the test user round_of_16 advancement picks (Phase 1 + Phase 2)
    that span WON R32 (green/banked), LOST R32 (red/missed) and PENDING R32
    (gold/in play) — so the R16 bar carries the three-colour split, with the
    two phases deliberately different shapes,
  * gives the user R32 match-score predictions (some finished → banked, some
    upcoming → best-case ≤) for the KO-matches strip.

Deeper rounds (QF→Winner) stay empty on purpose: their feeder fixtures are
still `slot:` placeholders, so there's no honest way to colour them yet.

Re-runnable: clears the user's round_of_16 picks + the touched match preds
first. DEV DB only.
"""
import asyncio

from sqlmodel import delete, select

from app.database import async_session_maker
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score, ScoreSource
from app.models.user import User

EMAIL = "test@example.com"

# R32 results to APPLY (home, away) -> (home_score, away_score). The existing
# South Korea 0-1 Canada stays as-is.
R32_RESULTS = {
    ("Germany", "Scotland"): (2, 1),       # Germany win
    ("Sweden", "Brazil"): (0, 2),          # Brazil win
    ("France", "Paraguay"): (3, 0),        # France win
    ("England", "Senegal"): (1, 0),        # England win
    ("Spain", "Argentina"): (2, 1),        # Spain win
    ("United States", "Netherlands"): (1, 2),  # Netherlands win
}

# round_of_16 advancement picks = "team reaches the R16" (wins its R32 match).
# green = team that WON its R32, red = team that LOST, gold = R32 still pending.
P1_R16 = ["Brazil", "France", "Spain", "Germany",        # green (won)
          "Argentina", "United States",                  # red (lost)
          "Belgium", "Switzerland", "Mexico", "Croatia"]  # gold (pending)
P2_R16 = ["Brazil", "France", "Spain", "England", "Netherlands",  # green (won)
          "Argentina",                                            # red (lost)
          "Belgium", "Croatia"]                                   # gold (pending)

# R32 match-score predictions. Finished → banked; scheduled → best-case ≤.
MATCH_PREDS = {
    ("South Korea", "Canada"): (0, 1),       # exact
    ("Germany", "Scotland"): (2, 1),         # exact
    ("Sweden", "Brazil"): (0, 1),            # outcome
    ("France", "Paraguay"): (2, 0),          # outcome
    ("England", "Senegal"): (1, 0),          # exact
    ("Spain", "Argentina"): (1, 2),          # miss
    ("United States", "Netherlands"): (1, 2),  # exact
    ("Morocco", "Japan"): (1, 1),            # upcoming → ≤
    ("Belgium", "Czechia"): (2, 0),          # upcoming → ≤
    ("Colombia", "Croatia"): (1, 1),         # upcoming → ≤
}


async def _fixture(s, home: str, away: str) -> Fixture | None:
    return (
        await s.execute(
            select(Fixture).where(
                Fixture.stage == "round_of_32",
                Fixture.home_team == home,
                Fixture.away_team == away,
            )
        )
    ).scalar_one_or_none()


async def main():
    async with async_session_maker() as s:
        user = (await s.execute(select(User).where(User.email == EMAIL))).scalar_one_or_none()
        if not user:
            raise SystemExit(f"no user {EMAIL}")

        # 1) finish the chosen R32 fixtures (idempotent: upsert score + status)
        applied = 0
        for (home, away), (hs, as_) in R32_RESULTS.items():
            fx = await _fixture(s, home, away)
            if not fx:
                print(f"  ! fixture not found: {home} vs {away}")
                continue
            fx.status = MatchStatus.FINISHED
            existing = (
                await s.execute(select(Score).where(Score.fixture_id == fx.id))
            ).scalar_one_or_none()
            if existing:
                existing.home_score, existing.away_score = hs, as_
            else:
                s.add(Score(fixture_id=fx.id, home_score=hs, away_score=as_, source=ScoreSource.MANUAL))
            applied += 1
        print(f"finished {applied} R32 fixtures")

        # 2) reset + insert round_of_16 advancement picks (both phases)
        await s.execute(
            delete(TeamPrediction).where(
                TeamPrediction.user_id == user.id,
                TeamPrediction.stage == "round_of_16",
            )
        )
        for team in P1_R16:
            s.add(TeamPrediction(user_id=user.id, team=team, stage="round_of_16",
                                 phase=PredictionPhase.PHASE_1))
        for team in P2_R16:
            s.add(TeamPrediction(user_id=user.id, team=team, stage="round_of_16",
                                 phase=PredictionPhase.PHASE_2))
        print(f"seeded R16 picks: P1={len(P1_R16)} P2={len(P2_R16)}")

        # 3) R32 match-score predictions for the strip (upsert per fixture)
        mp = 0
        for (home, away), (hs, as_) in MATCH_PREDS.items():
            fx = await _fixture(s, home, away)
            if not fx:
                print(f"  ! match fixture not found: {home} vs {away}")
                continue
            await s.execute(
                delete(MatchPrediction).where(
                    MatchPrediction.user_id == user.id,
                    MatchPrediction.fixture_id == fx.id,
                )
            )
            s.add(MatchPrediction(user_id=user.id, fixture_id=fx.id,
                                  home_score=hs, away_score=as_,
                                  phase=PredictionPhase.PHASE_2))
            mp += 1
        print(f"seeded {mp} R32 match-score predictions")

        await s.commit()
        print("done.")


asyncio.run(main())

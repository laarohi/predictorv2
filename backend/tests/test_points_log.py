"""Points-log builder (`services/points_log.build_points_log`).

The log is a per-event VIEW over the same scoring primitives the leaderboard
uses; nothing is persisted. The load-bearing test here is RECONCILIATION:
for every user, the sum of event points must equal
`calculate_user_points(...).total` — if the two ever disagree, the log is
lying about where points came from.

Scenario (one seeded mini-tournament, reused across tests):

- Group A (4 teams, 6 fixtures, complete): FRA 1st, GER 2nd, ITA 3rd, ESP 4th
- Group B (2 teams, 1 fixture, complete):  ARG 1st, BRA 2nd (1-1 draw →
  alphabetical tiebreak; FIFA rankings table is empty in tests)
- Best-8 thirds: ITA (the only 3rd-placed team) → qualifies via the cut
- R32: FRA beats BRA (1-0), ARG beats GER (1-1, pens 4-2 → outcome folds
  ET/pens; regulation stays X)
- R16: FRA vs ARG SCHEDULED → picks on it are pending, no events
- user1 has no Phase-2 bracket → the Phase-1→Phase-2 carry-forward fires;
  user2 has one real Phase-2 row → no fallback for them
- Bonus: first real YAML question answered right by user1, second answered
  wrong (miss event with the correct answers attached)
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.bonus import BonusAnswer, BonusPrediction
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score, ScoreSource
from app.models.user import AuthProvider, User
from app.services.bonus import get_questions
from app.services.points_log import build_points_log
from app.services.scoring import calculate_user_points


# Full deterministic config (logarithmic mode so the rarity bonus is
# exercised). Patched onto app.services.scoring — points_log calls through
# the scoring module, so the engine and the log always see the same config.
_CONFIG = {
    "mode": "logarithmic",
    "match": {"correct_outcome": 5, "exact_score": 10, "rarity_cap": 10, "hybrid_cap": 10},
    "advancement": {
        "round_of_32": 10,
        "round_of_16": 15,
        "quarter_final": 25,
        "semi_final": 55,
        "final": 85,
        "winner": 150,
        "group_position": 5,
        "phase_2": {
            "round_of_32": 0,
            "round_of_16": 5,
            "quarter_final": 15,
            "semi_final": 40,
            "final": 60,
            "winner": 100,
        },
    },
}

_TS = lambda d, h=18: datetime(2026, 6, d, h, 0, tzinfo=timezone.utc)  # noqa: E731
GROUP_A_END = _TS(25, 17)
GROUP_B_END = _TS(24, 20)
R32_FRA_BRA = _TS(29)
R32_ARG_GER = _TS(30)


@pytest.fixture(autouse=True)
def patch_scoring_config():
    with patch("app.services.scoring.get_scoring_config", return_value=_CONFIG):
        yield


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


def _fixture(
    session: AsyncSession,
    comp_id: UUID,
    *,
    stage: str,
    group: str | None = None,
    home: str,
    away: str,
    kickoff: datetime,
    status: MatchStatus = MatchStatus.FINISHED,
    hs: int | None = None,
    aws: int | None = None,
    het: int | None = None,
    aet: int | None = None,
    hp: int | None = None,
    ap: int | None = None,
) -> Fixture:
    fx = Fixture(
        competition_id=comp_id,
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        stage=stage,
        group=group,
        status=status,
    )
    session.add(fx)
    if hs is not None and aws is not None:
        session.add(
            Score(
                fixture=fx,
                home_score=hs,
                away_score=aws,
                home_score_et=het,
                away_score_et=aet,
                home_penalties=hp,
                away_penalties=ap,
                source=ScoreSource.API,
            )
        )
    return fx


@pytest_asyncio.fixture
async def scenario(session: AsyncSession) -> dict:
    comp = Competition(name="WC2026", entry_fee=Decimal("0"), external_id="WC")
    session.add(comp)
    u1 = User(email="u1@x.com", name="U1", password_hash="x", auth_provider=AuthProvider.EMAIL)
    u2 = User(email="u2@x.com", name="U2", password_hash="x", auth_provider=AuthProvider.EMAIL)
    u3 = User(email="u3@x.com", name="U3", password_hash="x", auth_provider=AuthProvider.EMAIL)
    session.add_all([u1, u2, u3])
    await session.commit()
    for obj in (comp, u1, u2, u3):
        await session.refresh(obj)

    # Group A: FRA 9pts, GER 6, ITA 3, ESP 0 — no ties.
    a1 = _fixture(session, comp.id, stage="group", group="A", home="France", away="Germany",
                  kickoff=_TS(15), hs=2, aws=0)
    _fixture(session, comp.id, stage="group", group="A", home="France", away="Italy",
             kickoff=_TS(18), hs=2, aws=1)
    _fixture(session, comp.id, stage="group", group="A", home="Germany", away="Italy",
             kickoff=_TS(19), hs=1, aws=0)
    _fixture(session, comp.id, stage="group", group="A", home="France", away="Spain",
             kickoff=_TS(20), hs=3, aws=0)
    _fixture(session, comp.id, stage="group", group="A", home="Germany", away="Spain",
             kickoff=_TS(22), hs=2, aws=0)
    _fixture(session, comp.id, stage="group", group="A", home="Italy", away="Spain",
             kickoff=GROUP_A_END, hs=1, aws=0)
    # Group B: 1-1 draw → alphabetical tiebreak → ARG 1st, BRA 2nd.
    b1 = _fixture(session, comp.id, stage="group", group="B", home="Argentina", away="Brazil",
                  kickoff=GROUP_B_END, hs=1, aws=1)
    # Knockouts: FRA beats BRA; ARG beats GER on penalties (regulation 1-1).
    k1 = _fixture(session, comp.id, stage="round_of_32", home="France", away="Brazil",
                  kickoff=R32_FRA_BRA, hs=1, aws=0)
    k2 = _fixture(session, comp.id, stage="round_of_32", home="Argentina", away="Germany",
                  kickoff=R32_ARG_GER, hs=1, aws=1, het=1, aet=1, hp=4, ap=2)
    # R16 scheduled — everything predicted on it stays pending.
    _fixture(session, comp.id, stage="round_of_16", home="France", away="Argentina",
             kickoff=datetime(2026, 7, 3, 18, 0, tzinfo=timezone.utc))
    await session.commit()

    def mp(user, fx, h, a, phase=PredictionPhase.PHASE_1):
        session.add(MatchPrediction(user_id=user.id, fixture_id=fx.id,
                                    home_score=h, away_score=a, phase=phase))

    def tp(user, team, stage, phase=PredictionPhase.PHASE_1):
        session.add(TeamPrediction(user_id=user.id, team=team, stage=stage, phase=phase))

    # user1 — the rich case.
    mp(u1, a1, 2, 0)                                   # exact
    mp(u1, b1, 2, 1)                                   # miss
    mp(u1, k1, 1, 0, PredictionPhase.PHASE_2)          # exact (regulation)
    mp(u1, k2, 1, 1, PredictionPhase.PHASE_2)          # exact (regulation 1-1)
    tp(u1, "France", "round_of_32")
    tp(u1, "Italy", "round_of_32")                     # qualifies via thirds
    tp(u1, "Spain", "round_of_32")                     # 4th — dead at group end
    tp(u1, "France", "round_of_16")                    # earned + P2 carry-forward
    tp(u1, "Brazil", "round_of_16")                    # out at R32
    tp(u1, "Germany", "round_of_16")                   # out at R32 (pens)
    tp(u1, "France", "winner")                         # pending — no event
    tp(u1, "Argentina", "quarter_final")               # pending — no event

    # user2 — has a real Phase-2 bracket row → NO carry-forward.
    mp(u2, a1, 1, 0)                                   # outcome only
    mp(u2, b1, 1, 1)                                   # exact + rarity (1 of 3)
    tp(u2, "France", "round_of_16")
    tp(u2, "France", "round_of_16", PredictionPhase.PHASE_2)

    # user3 — misses only.
    mp(u3, a1, 0, 1)
    mp(u3, b1, 1, 0)

    # Bonus: first real YAML question right, second wrong (for user1).
    questions = get_questions()
    q1, q2 = questions[0], questions[1]
    session.add(BonusAnswer(competition_id=comp.id, question_id=q1.id,
                            correct_answer="Morocco",
                            resolved_at=datetime(2026, 6, 28, 9, 0, tzinfo=timezone.utc)))
    session.add(BonusAnswer(competition_id=comp.id, question_id=q2.id,
                            correct_answer="Japan",
                            resolved_at=datetime(2026, 6, 28, 10, 0, tzinfo=timezone.utc)))
    session.add(BonusPrediction(user_id=u1.id, question_id=q1.id, answer="Morocco"))
    session.add(BonusPrediction(user_id=u1.id, question_id=q2.id, answer="Senegal"))
    await session.commit()

    return {"users": [u1, u2, u3], "q1": q1, "q2": q2}


async def test_log_reconciles_with_leaderboard_for_every_user(session, scenario):
    """THE invariant: sum of log events == the engine's total, per user."""
    for user in scenario["users"]:
        events = await build_points_log(session, user.id)
        breakdown = await calculate_user_points(session, user.id)
        assert sum(e.points for e in events) == breakdown.total, user.name


async def test_events_sorted_newest_first(session, scenario):
    events = await build_points_log(session, scenario["users"][0].id)
    assert events, "expected events for user1"
    stamps = [e.ts for e in events]
    assert stamps == sorted(stamps, reverse=True)


async def test_match_event_shape(session, scenario):
    u1 = scenario["users"][0]
    events = {e.id: e for e in await build_points_log(session, u1.id)}

    exact = next(e for e in events.values()
                 if e.kind == "match" and e.home_team == "France" and e.group == "A")
    assert exact.points == 15 and exact.result == "exact" and not exact.is_miss
    assert {(c.label, c.points) for c in exact.chips} == {("Outcome", 5), ("Exact score", 10)}
    assert exact.ts == _TS(15)
    assert exact.phase == "phase_1"

    miss = next(e for e in events.values() if e.kind == "match" and e.group == "B")
    assert miss.points == 0 and miss.is_miss and miss.result == "miss" and miss.chips == []


async def test_rarity_chip_on_contrarian_exact(session, scenario):
    """user2's 1-1 on the group B draw: 1 of 3 predictors right → rarity +1."""
    u2 = scenario["users"][1]
    events = await build_points_log(session, u2.id)
    b1 = next(e for e in events if e.kind == "match" and e.group == "B")
    assert b1.points == 16  # 5 outcome + 10 exact + 1 rarity
    assert ("Rarity bonus", 1) in {(c.label, c.points) for c in b1.chips}


async def test_qualification_events(session, scenario):
    u1 = scenario["users"][0]
    events = {e.id: e for e in await build_points_log(session, u1.id)}

    # FRA: R32 pick (+10) with the exact-position bonus folded in (+5).
    fra = events["adv:round_of_32:France"]
    assert fra.points == 15 and not fra.is_miss
    assert fra.ts == GROUP_A_END
    assert fra.predicted_position == 1 and fra.actual_position == 1
    # Phase-2 R32 is worth 0, so the carry-forward must NOT flag R32 events.
    assert not fra.p2_fallback and fra.phase == "phase_1"

    # ITA: qualified via the best-8-thirds cut — anchored to the LAST group
    # kickoff overall, flagged third_place, no position bonus (user1's
    # predicted table never placed Italy).
    ita = events["adv:round_of_32:Italy"]
    assert ita.points == 10 and ita.third_place and ita.ts == GROUP_A_END

    # ESP: picked into R32, finished 4th → miss at group completion.
    esp = events["adv:round_of_32:Spain"]
    assert esp.is_miss and esp.points == 0 and esp.elim_stage == "group"
    assert esp.ts == GROUP_A_END

    # GER earned the +5 position bonus without an R32 pick → standalone event.
    ger = events["adv:round_of_32:Germany"]
    assert ger.points == 5 and not ger.is_miss
    assert [c.label for c in ger.chips] == ["Exact position"]


async def test_ko_advancement_with_p2_carry_forward(session, scenario):
    u1 = scenario["users"][0]
    events = {e.id: e for e in await build_points_log(session, u1.id)}

    # FRA reached R16 by winning the R32 match: P1 +15, carried P2 +5.
    fra = events["adv:round_of_16:France"]
    assert fra.points == 20 and fra.phase == "both" and fra.p2_fallback
    assert fra.ts == R32_FRA_BRA
    labels = {c.label for c in fra.chips}
    assert labels == {"Phase I", "Phase II · carried"}

    # BRA out at R32 → the R16 pick is a dead miss anchored to that loss.
    bra = events["adv:round_of_16:Brazil"]
    assert bra.is_miss and bra.elim_stage == "round_of_32" and bra.ts == R32_FRA_BRA

    # GER lost on PENALTIES — the folded outcome must still register the elimination.
    ger = events["adv:round_of_16:Germany"]
    assert ger.is_miss and ger.elim_stage == "round_of_32" and ger.ts == R32_ARG_GER

    # Open fates emit nothing: FRA winner + ARG quarter-final are pending.
    assert "adv:winner:France" not in events
    assert "adv:quarter_final:Argentina" not in events


async def test_real_p2_bracket_suppresses_carry_forward(session, scenario):
    u2 = scenario["users"][1]
    events = {e.id: e for e in await build_points_log(session, u2.id)}
    fra = events["adv:round_of_16:France"]
    assert fra.points == 20 and fra.phase == "both" and not fra.p2_fallback
    assert {c.label for c in fra.chips} == {"Phase I", "Phase II"}


async def test_bonus_events(session, scenario):
    u1 = scenario["users"][0]
    q1, q2 = scenario["q1"], scenario["q2"]
    events = {e.id: e for e in await build_points_log(session, u1.id)}

    hit = events[f"bonus:{q1.id}"]
    assert hit.points == q1.points and not hit.is_miss
    assert hit.answer == "Morocco"
    assert hit.ts == datetime(2026, 6, 28, 9, 0, tzinfo=timezone.utc)

    miss = events[f"bonus:{q2.id}"]
    assert miss.is_miss and miss.points == 0
    assert miss.answer == "Senegal" and miss.correct_answers == ["Japan"]


async def test_user_with_no_predictions_has_empty_log(session, scenario):
    ghost_free = User(email="new@x.com", name="New", password_hash="x",
                      auth_provider=AuthProvider.EMAIL)
    session.add(ghost_free)
    await session.commit()
    await session.refresh(ghost_free)
    assert await build_points_log(session, ghost_free.id) == []

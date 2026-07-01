"""get_bonus_results() — the per-question detail behind calculate_bonus_points().

Feeds the standings breakdown panel's "which bonus questions did I get
right, and for how many points" list.
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.bonus import BonusAnswer, BonusPrediction
from app.models.competition import Competition
from app.models.user import User
from app.services.bonus import calculate_bonus_points, get_bonus_results, get_questions


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _comp_and_user(session: AsyncSession) -> tuple[Competition, User]:
    comp = Competition(name="WC2026", entry_fee=Decimal("0"), external_id="WC", is_active=True)
    user = User(email="bonus@example.com", name="bonus")
    session.add_all([comp, user])
    await session.commit()
    await session.refresh(comp)
    await session.refresh(user)
    return comp, user


@pytest.mark.asyncio
async def test_correct_answer_appears_with_its_points(session):
    comp, user = await _comp_and_user(session)
    dark_horse = next(q for q in get_questions() if q.id == "dark_horse")

    session.add(BonusAnswer(competition_id=comp.id, question_id="dark_horse", correct_answer="Morocco"))
    session.add(BonusPrediction(user_id=user.id, question_id="dark_horse", answer="Morocco"))
    await session.commit()

    results = await get_bonus_results(session, user.id)
    assert len(results) == 1
    assert results[0].question_id == "dark_horse"
    assert results[0].label == dark_horse.label
    assert results[0].points == dark_horse.points
    assert await calculate_bonus_points(session, user.id) == dark_horse.points


@pytest.mark.asyncio
async def test_wrong_answer_is_excluded(session):
    comp, user = await _comp_and_user(session)
    session.add(BonusAnswer(competition_id=comp.id, question_id="dark_horse", correct_answer="Morocco"))
    session.add(BonusPrediction(user_id=user.id, question_id="dark_horse", answer="Japan"))
    await session.commit()

    assert await get_bonus_results(session, user.id) == []
    assert await calculate_bonus_points(session, user.id) == 0


@pytest.mark.asyncio
async def test_unanswered_question_is_excluded(session):
    comp, user = await _comp_and_user(session)
    # Graded question exists, but the user never submitted a prediction for it.
    session.add(BonusAnswer(competition_id=comp.id, question_id="dark_horse", correct_answer="Morocco"))
    await session.commit()

    assert await get_bonus_results(session, user.id) == []
    assert await calculate_bonus_points(session, user.id) == 0


@pytest.mark.asyncio
async def test_multiple_correct_answers_all_listed(session):
    comp, user = await _comp_and_user(session)
    dark_horse = next(q for q in get_questions() if q.id == "dark_horse")
    flop = next(q for q in get_questions() if q.id == "flop")

    session.add(BonusAnswer(competition_id=comp.id, question_id="dark_horse", correct_answer="Morocco"))
    session.add(BonusAnswer(competition_id=comp.id, question_id="flop", correct_answer="Germany"))
    session.add(BonusPrediction(user_id=user.id, question_id="dark_horse", answer="Morocco"))
    session.add(BonusPrediction(user_id=user.id, question_id="flop", answer="Germany"))
    await session.commit()

    results = await get_bonus_results(session, user.id)
    assert {r.question_id for r in results} == {"dark_horse", "flop"}
    assert await calculate_bonus_points(session, user.id) == dark_horse.points + flop.points

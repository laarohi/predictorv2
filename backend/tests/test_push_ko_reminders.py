"""Tests for the Phase 2 knockout per-match lock reminder push trigger.

`send_knockout_lock_reminders` fires while a knockout match's lock is within
`_KO_REMINDER_LEAD_MIN` (60) minutes — up to ~1h before lock — and only nudges
subscribers who HAVEN'T predicted that fixture. It must be idempotent (one
PushSend per user/fixture, so the 60s scheduler tick can't spam), must skip
matches outside the window, must skip unresolved 'slot:' placeholders, and
must do nothing while Phase 2 is inactive.

Real in-memory SQLite + a no-op send patch (the trigger leans on the
per-fixture window query + the PushSend idempotency rows, so mocks would test
nothing).
"""

import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

import app.services.push_triggers as pt
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.push_send import PushSend
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.push_triggers import KIND_KO_LOCK, send_knockout_lock_reminders


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.fixture(autouse=True)
def _no_real_push(monkeypatch):
    """Record-only: never attempt a real Web Push send in tests."""

    async def _noop(session, user_id, payload):
        return None

    monkeypatch.setattr(pt, "send_to_user", _noop)


async def _subscriber(session: AsyncSession, email: str) -> User:
    u = User(email=email, name=email.split("@")[0], is_active=True)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    session.add(
        PushSubscription(
            user_id=u.id,
            endpoint=f"https://push.example/{uuid.uuid4()}",
            p256dh="key",
            auth="auth",
            active=True,
        )
    )
    await session.commit()
    return u


async def _reminded(session: AsyncSession, ref_id) -> set:
    rows = await session.execute(
        select(PushSend.user_id).where(
            PushSend.kind == KIND_KO_LOCK, PushSend.ref_id == ref_id
        )
    )
    return set(rows.scalars().all())


@pytest_asyncio.fixture
async def setup(session: AsyncSession):
    now = utc_now()
    comp = Competition(name="WC2026", is_active=True, is_phase2_active=True)
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    # In-window: kickoff 30 min away → lock in ~15 min → inside the 60-min lead.
    in_window = Fixture(
        competition_id=comp.id, home_team="Brazil", away_team="Japan",
        kickoff=now + timedelta(minutes=30), stage="round_of_32",
        status=MatchStatus.SCHEDULED,
    )
    # Far: kickoff 3h away → not yet in the reminder window.
    far = Fixture(
        competition_id=comp.id, home_team="Spain", away_team="Italy",
        kickoff=now + timedelta(hours=3), stage="round_of_32",
        status=MatchStatus.SCHEDULED,
    )
    # Placeholder (unresolved) but in-window → must be skipped (no 'slot:' body).
    placeholder = Fixture(
        competition_id=comp.id,
        home_team="slot:round_of_16:1:home", away_team="slot:round_of_16:1:away",
        kickoff=now + timedelta(minutes=30), stage="round_of_16",
        status=MatchStatus.SCHEDULED,
    )
    session.add_all([in_window, far, placeholder])
    await session.commit()
    for f in (in_window, far, placeholder):
        await session.refresh(f)

    alice = await _subscriber(session, "alice@example.com")  # predicted in_window
    bob = await _subscriber(session, "bob@example.com")  # did NOT predict
    session.add(
        MatchPrediction(
            user_id=alice.id, fixture_id=in_window.id,
            home_score=1, away_score=0, phase=PredictionPhase.PHASE_2,
        )
    )
    await session.commit()
    return {
        "comp": comp, "in_window": in_window, "far": far,
        "placeholder": placeholder, "alice": alice, "bob": bob,
    }


@pytest.mark.asyncio
async def test_reminds_only_the_missing_subscriber(session, setup):
    await send_knockout_lock_reminders(session)
    sent = await _reminded(session, setup["in_window"].id)
    assert setup["bob"].id in sent  # missing pick → reminded
    assert setup["alice"].id not in sent  # already predicted → not reminded


@pytest.mark.asyncio
async def test_skips_out_of_window_and_placeholder_fixtures(session, setup):
    await send_knockout_lock_reminders(session)
    assert await _reminded(session, setup["far"].id) == set()  # 3h away
    assert await _reminded(session, setup["placeholder"].id) == set()  # slot: placeholder


@pytest.mark.asyncio
async def test_idempotent_across_ticks(session, setup):
    await send_knockout_lock_reminders(session)
    first = await _reminded(session, setup["in_window"].id)
    await send_knockout_lock_reminders(session)  # next 60s tick
    second = await _reminded(session, setup["in_window"].id)
    assert first == second  # no duplicate sends


@pytest.mark.asyncio
async def test_noop_when_phase2_inactive(session, setup):
    setup["comp"].is_phase2_active = False
    session.add(setup["comp"])
    await session.commit()
    await send_knockout_lock_reminders(session)
    assert await _reminded(session, setup["in_window"].id) == set()

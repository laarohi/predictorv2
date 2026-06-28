"""The 90-minute freeze for knockout extra time (score_sync._score_fields_for).

Knockout SCORE grading is on the 90' result (Score.regulation_outcome =
home_score vs away_score). ESPN — our live source — reports ONE running total
with ET goals folded into home_score/away_score and exposes no 90' split, only
the period: regulation full-time = period 2, ET/shootout = period > 2 (verified
against real ESPN payloads, incl. the 2022 final at period 5 / STATUS_FINAL_PEN).

So once a knockout fixture passes regulation we must freeze home_score/away_score
at the captured 90' value and route the running total to *_et — keeping
regulation_outcome true to 90' while outcome/advancement still resolve via
ET → penalties.
"""

import uuid
from types import SimpleNamespace

from app.models.fixture import MatchStatus
from app.services.external_scores import ExternalScore
from app.services.score_sync import _score_fields_for


def _fx(stage: str):
    return SimpleNamespace(id=uuid.uuid4(), stage=stage)


def _ext(home, away, *, period=None, home_et=None, away_et=None, home_pen=None, away_pen=None):
    return ExternalScore(
        external_id="",
        home_team="A",
        away_team="B",
        home_score=home,
        away_score=away,
        status=MatchStatus.LIVE,
        period=period,
        home_score_et=home_et,
        away_score_et=away_et,
        home_penalties=home_pen,
        away_penalties=away_pen,
    )


def _existing(home, away):
    return SimpleNamespace(home_score=home, away_score=away)


def test_group_fixture_passes_through():
    # Group matches never have ET — straight pass-through regardless of period.
    assert _score_fields_for(_fx("group"), _ext(2, 1, period=2), None) == (
        2, 1, None, None, None, None,
    )


def test_knockout_in_regulation_passes_through():
    # period 2 = still regulation; the running total IS the live 90' score.
    assert _score_fields_for(
        _fx("round_of_32"), _ext(1, 1, period=2), _existing(1, 0)
    ) == (1, 1, None, None, None, None)


def test_knockout_extra_time_freezes_90min():
    # 1-1 at 90' (captured in `existing`), then a 2-1 ET goal (period 3).
    fields = _score_fields_for(_fx("round_of_32"), _ext(2, 1, period=3), _existing(1, 1))
    # home/away frozen at the 90' 1-1; the 2-1 running total → *_et.
    assert fields == (1, 1, 2, 1, None, None)


def test_knockout_shootout_freezes_and_keeps_pens():
    # The 2022-final shape: 2-2 at 90' (captured), 3-3 AET, shootout 4-2, period 5.
    fields = _score_fields_for(
        _fx("final"), _ext(3, 3, period=5, home_pen=4, away_pen=2), _existing(2, 2)
    )
    assert fields == (2, 2, 3, 3, 4, 2)


def test_knockout_extra_time_no_prior_score_degrades_gracefully():
    # Never observed regulation (polling gap) → best-effort running total for
    # both home/away + *_et, and a warning (asserted elsewhere via logs). No
    # crash, no null home_score.
    fields = _score_fields_for(_fx("round_of_16"), _ext(2, 1, period=4), None)
    assert fields == (2, 1, 2, 1, None, None)


def test_knockout_period_none_passes_through():
    # A provider that doesn't expose period (Football-Data) carries its own ET
    # split — take the normal path untouched.
    fields = _score_fields_for(
        _fx("final"), _ext(1, 1, period=None, home_et=2, away_et=1), _existing(1, 1)
    )
    assert fields == (1, 1, 2, 1, None, None)


def test_knockout_explicit_et_split_preferred_over_running_total():
    # period > 2 but the provider DID give an explicit ET split — prefer it over
    # treating the running total as the ET score.
    fields = _score_fields_for(
        _fx("quarter_final"), _ext(1, 1, period=3, home_et=2, away_et=1), _existing(1, 1)
    )
    assert fields == (1, 1, 2, 1, None, None)


# ── integration: a regulation → extra-time tick sequence through the apply layer ──

from datetime import datetime, timezone  # noqa: E402
from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlmodel import SQLModel, select  # noqa: E402

from app.models.competition import Competition  # noqa: E402
from app.models.fixture import Fixture  # noqa: E402
from app.models.score import Score  # noqa: E402
from app.services.score_sync import ScoreSyncResult, _apply_external_score  # noqa: E402


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(session: AsyncSession) -> Competition:
    comp = Competition(name="WC2026", entry_fee=Decimal("0"), external_id="WC")
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


def _ko_ext(home, away, *, period, home_pen=None, away_pen=None):
    return ExternalScore(
        external_id="",
        home_team="Mexico",
        away_team="South Africa",
        home_score=home,
        away_score=away,
        status=MatchStatus.LIVE,
        period=period,
        home_penalties=home_pen,
        away_penalties=away_pen,
        final_authoritative=False,
    )


@pytest.mark.asyncio
async def test_apply_freezes_90min_across_regulation_then_extra_time(session, competition):
    """The real scenario: a knockout ticks through regulation, then ET. The
    stored 90' score must freeze so regulation_outcome grades the 90' result,
    while outcome resolves advancement via ET."""
    fx = Fixture(
        competition_id=competition.id,
        external_id="ko1",
        home_team="Mexico",
        away_team="South Africa",
        kickoff=datetime(2026, 7, 4, 19, 0, tzinfo=timezone.utc),
        stage="round_of_32",
        group=None,
        status=MatchStatus.LIVE,
    )
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    res = ScoreSyncResult()

    # Regulation tick — 1-1 at the 90' mark (period 2).
    await _apply_external_score(session, competition.id, _ko_ext(1, 1, period=2), res)
    await session.commit()
    score = (
        await session.execute(select(Score).where(Score.fixture_id == fx.id))
    ).scalar_one()
    assert (score.home_score, score.away_score) == (1, 1)
    assert score.home_score_et is None

    # Extra-time tick — ESPN's running total is now 2-1 (period 3).
    await _apply_external_score(session, competition.id, _ko_ext(2, 1, period=3), res)
    await session.commit()
    await session.refresh(score)

    # 90' frozen at 1-1; the running total lands in *_et.
    assert (score.home_score, score.away_score) == (1, 1)
    assert (score.home_score_et, score.away_score_et) == (2, 1)
    # Grading sees the true 90' draw; advancement sees the ET winner.
    assert score.regulation_outcome == "X"
    assert score.outcome == "1"


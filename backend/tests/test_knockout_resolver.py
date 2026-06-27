"""Tests for the knockout bracket resolver.

Covers:
  * PARITY / golden R32: a known standings set → exactly the 16 expected R32
    matchups produced by the official FIFA 2026 routing. The expected pairs
    are derived independently (mirroring frontend bracketResolver.ts) inside
    this test, so a divergence between the backend resolver and the frontend
    routing fails the test.
  * external_id ↔ FIFA match_number bijection: all 32 ids map to distinct
    match numbers covering 73-104.
  * apply_knockout_resolution: stamps R32 onto the real fixture rows only once
    all group fixtures are FINISHED; idempotent (second run is a no-op);
    preserves kickoff / external_id; backfills match_number.
  * later-round resolution: given R32 Scores, the correct R16 teams get
    stamped from the actual winners.

Seeding model (mirrors tests/test_bracket_consistency.py): groups A–L, teams
"<G>1".."<G>4"; <G>1 wins all (9 pts, 1st), <G>2 wins twice (6 pts, 2nd),
<G>3 beats <G>4 by (12 - group_index) goals so third-place goal difference
falls A→L — the thirds of groups A–H qualify, I–L miss. Fully deterministic,
no ties. Under this set the qualifying-third combination is "ABCDEFGH".
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource
from app.services.knockout_resolver import (
    ALL_KNOCKOUT_MATCH_NUMBERS,
    EXTERNAL_ID_BY_MATCH_NUMBER,
    MATCH_NUMBER_BY_EXTERNAL_ID,
    R16_FEEDS,
    R32_SEEDS,
    THIRD_SLOT_KEY,
    apply_knockout_resolution,
    compute_r32_matchups,
)

KICKOFF = datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)
KO_KICKOFF = datetime(2026, 6, 28, 19, 0, tzinfo=timezone.utc)
GROUPS = list("ABCDEFGHIJKL")


# ---------------------------------------------------------------------------
# Independent golden derivation (mirrors frontend bracketResolver routing)
# ---------------------------------------------------------------------------

# frontend MATCH_TO_WINNER_KEY (bracketResolver.ts) — must equal THIRD_SLOT_KEY.
_FRONTEND_MATCH_TO_WINNER_KEY = {
    74: "1E", 77: "1I", 79: "1A", 80: "1L",
    81: "1D", 82: "1G", 85: "1B", 87: "1K",
}


def _load_grid() -> dict[str, dict[str, str]]:
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        for rel in (
            "scripts/data/third_place_mapping.json",
            "frontend/src/lib/config/thirdPlaceMapping.json",
        ):
            p = parent / rel
            if p.exists():
                return json.loads(p.read_text())
    raise FileNotFoundError("third-place mapping not found")


def _expected_r32_for_abcdefgh() -> dict[int, tuple[str, str]]:
    """Golden R32 pairs for the test standings (thirds A–H qualify), derived
    by independently re-running the frontend routing over team names <G>1.."""
    grid = _load_grid()["ABCDEFGH"]
    positions = {f"{i+1}{g}": f"{g}{i+1}" for g in GROUPS for i in range(4)}
    third_by_group = {g: f"{g}3" for g in "ABCDEFGH"}

    def resolve(spec: str, m: int) -> str:
        if spec == "T":
            target = grid[_FRONTEND_MATCH_TO_WINNER_KEY[m]]  # "3X"
            return third_by_group[target[1:]]
        return positions[spec]

    return {
        m: (resolve(h, m), resolve(a, m)) for m, (h, a) in R32_SEEDS.items()
    }


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Per-test in-memory SQLite session. Mirrors test_standings.py."""
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


def _group_results(gi: int) -> list[tuple[str, str, int, int]]:
    """The six matches of group index `gi` as (home, away, hs, as)."""
    g = GROUPS[gi]
    t = [f"{g}{n}" for n in (1, 2, 3, 4)]
    return [
        (t[0], t[1], 3, 0),
        (t[0], t[2], 3, 0),
        (t[0], t[3], 3, 0),
        (t[1], t[2], 2, 0),
        (t[1], t[3], 2, 0),
        (t[2], t[3], 12 - gi, 0),  # third-place GD falls A→L: A–H thirds qualify
    ]


async def _seed_finished_groups(
    session: AsyncSession, competition: Competition
) -> None:
    """Create all 72 group fixtures FINISHED with scores → final standings."""
    for gi in range(len(GROUPS)):
        for home, away, hs, aws in _group_results(gi):
            fixture = Fixture(
                competition_id=competition.id,
                home_team=home,
                away_team=away,
                kickoff=KICKOFF,
                stage="group",
                group=GROUPS[gi],
                status=MatchStatus.FINISHED,
            )
            session.add(fixture)
            session.add(
                Score(
                    fixture=fixture,
                    home_score=hs,
                    away_score=aws,
                    source=ScoreSource.API,
                )
            )
    await session.commit()


async def _seed_knockout_placeholders(
    session: AsyncSession, competition: Competition
) -> dict[str, Fixture]:
    """Create the 32 knockout fixture rows with placeholder team names,
    distinct kickoffs, external_ids set, and match_number NULL — mirroring the
    real seeded DB. Returns {external_id: fixture}."""
    out: dict[str, Fixture] = {}
    for i, (ext_id, mn) in enumerate(sorted(MATCH_NUMBER_BY_EXTERNAL_ID.items())):
        stage = (
            "round_of_32" if 73 <= mn <= 88
            else "round_of_16" if 89 <= mn <= 96
            else "quarter_final" if 97 <= mn <= 100
            else "semi_final" if 101 <= mn <= 102
            else "third_place" if mn == 103
            else "final"
        )
        fx = Fixture(
            competition_id=competition.id,
            home_team=f"slot:{stage}:{ext_id}:home",
            away_team=f"slot:{stage}:{ext_id}:away",
            kickoff=KO_KICKOFF + timedelta(hours=i),
            stage=stage,
            group=None,
            match_number=None,
            external_id=ext_id,
            status=MatchStatus.SCHEDULED,
        )
        session.add(fx)
        out[ext_id] = fx
    await session.commit()
    return out


# ---------------------------------------------------------------------------
# Map integrity
# ---------------------------------------------------------------------------


def test_match_number_bijection() -> None:
    """All 32 external_ids map to distinct match numbers covering 73-104."""
    assert len(MATCH_NUMBER_BY_EXTERNAL_ID) == 32
    match_numbers = list(MATCH_NUMBER_BY_EXTERNAL_ID.values())
    assert len(set(match_numbers)) == 32, "duplicate match numbers in map"
    assert set(match_numbers) == set(range(73, 105)), "must cover 73-104"
    # Inverse map round-trips.
    assert len(EXTERNAL_ID_BY_MATCH_NUMBER) == 32
    for ext, mn in MATCH_NUMBER_BY_EXTERNAL_ID.items():
        assert EXTERNAL_ID_BY_MATCH_NUMBER[mn] == ext


def test_match_number_anchors() -> None:
    """The known FD-id anchors pin the map: Final=104, 3rd=103, SFs=101/102."""
    assert MATCH_NUMBER_BY_EXTERNAL_ID["537390"] == 104  # FINAL
    assert MATCH_NUMBER_BY_EXTERNAL_ID["537389"] == 103  # THIRD_PLACE
    assert MATCH_NUMBER_BY_EXTERNAL_ID["537387"] == 101  # SEMI_FINAL 1
    assert MATCH_NUMBER_BY_EXTERNAL_ID["537388"] == 102  # SEMI_FINAL 2


def test_third_slot_key_matches_frontend() -> None:
    """THIRD_SLOT_KEY must equal the frontend MATCH_TO_WINNER_KEY."""
    assert THIRD_SLOT_KEY == _FRONTEND_MATCH_TO_WINNER_KEY


# ---------------------------------------------------------------------------
# Pure R32 computation (golden parity)
# ---------------------------------------------------------------------------


async def test_compute_r32_matchups_golden_parity(session, competition) -> None:
    """compute_r32_matchups over the test standings == the frontend routing's
    16 expected pairs, exactly."""
    from app.services.standings import (
        get_actual_group_standings,
        get_qualifying_third_place_teams,
    )

    await _seed_finished_groups(session, competition)
    standings = await get_actual_group_standings(session)
    thirds = await get_qualifying_third_place_teams(session)

    # Qualifying-third combination is exactly A–H.
    assert sorted(t["group"] for t in thirds) == list("ABCDEFGH")

    matchups = compute_r32_matchups(standings, thirds)
    expected = _expected_r32_for_abcdefgh()

    assert set(matchups.keys()) == set(range(73, 89))
    assert matchups == expected


# ---------------------------------------------------------------------------
# apply_knockout_resolution
# ---------------------------------------------------------------------------


async def test_apply_does_nothing_before_groups_finish(session, competition) -> None:
    """No R32 stamping while any group fixture is still unfinished. (We still
    backfill match_number, but never team names.)"""
    # Seed groups as SCHEDULED (not finished).
    for gi in range(len(GROUPS)):
        for home, away, hs, aws in _group_results(gi):
            session.add(
                Fixture(
                    competition_id=competition.id,
                    home_team=home,
                    away_team=away,
                    kickoff=KICKOFF,
                    stage="group",
                    group=GROUPS[gi],
                    status=MatchStatus.SCHEDULED,
                )
            )
    await session.commit()
    await _seed_knockout_placeholders(session, competition)

    report = await apply_knockout_resolution(session, competition, dry_run=False)

    assert report.groups_complete is False
    assert report.r32_resolved is False
    # No team-name changes; placeholders intact.
    rows = (
        await session.execute(
            select(Fixture).where(Fixture.stage == "round_of_32")
        )
    ).scalars().all()
    assert all(f.home_team.startswith("slot:") for f in rows)
    # match_number backfilled even pre-resolution.
    for f in rows:
        assert f.match_number == MATCH_NUMBER_BY_EXTERNAL_ID[f.external_id]


async def test_apply_stamps_r32_and_is_idempotent(session, competition) -> None:
    await _seed_finished_groups(session, competition)
    ext_to_fx = await _seed_knockout_placeholders(session, competition)
    kickoffs_before = {ext: fx.kickoff for ext, fx in ext_to_fx.items()}

    report = await apply_knockout_resolution(session, competition, dry_run=False)

    assert report.groups_complete is True
    assert report.r32_resolved is True
    # 16 R32 rows get teams + match_number stamped; the other 16 knockout rows
    # (R16-Final, not yet resolvable) get only their NULL match_number
    # backfilled. 16 + 16 = 32 changed rows.
    assert report.changed_count == 32

    expected = _expected_r32_for_abcdefgh()
    # Verify each R32 row now carries the real teams + match_number, kickoff
    # and external_id untouched.
    rows = (
        await session.execute(
            select(Fixture).where(Fixture.stage == "round_of_32")
        )
    ).scalars().all()
    assert len(rows) == 16
    for f in rows:
        mn = MATCH_NUMBER_BY_EXTERNAL_ID[f.external_id]
        assert f.match_number == mn
        assert (f.home_team, f.away_team) == expected[mn]
        assert f.kickoff == kickoffs_before[f.external_id]  # kickoff preserved

    # Idempotent: a second apply with the same results changes nothing.
    report2 = await apply_knockout_resolution(session, competition, dry_run=False)
    assert report2.changed_count == 0


async def test_dry_run_commits_nothing(session, competition) -> None:
    await _seed_finished_groups(session, competition)
    await _seed_knockout_placeholders(session, competition)

    report = await apply_knockout_resolution(session, competition, dry_run=True)
    assert report.dry_run is True
    assert report.r32_resolved is True
    assert report.changed_count > 0
    # Full computed table is present for preview.
    assert set(range(73, 89)).issubset(set(report.matchups.keys()))

    # Nothing was committed: R32 rows still placeholders, match_number NULL.
    rows = (
        await session.execute(
            select(Fixture).where(Fixture.stage == "round_of_32")
        )
    ).scalars().all()
    assert all(f.home_team.startswith("slot:") for f in rows)
    assert all(f.match_number is None for f in rows)


async def test_later_round_resolution_from_r32_results(session, competition) -> None:
    """Given FINISHED R32 Scores, the correct R16 teams get stamped from the
    actual winners (feeder winner/away resolution incl. the outcome property)."""
    await _seed_finished_groups(session, competition)
    ext_to_fx = await _seed_knockout_placeholders(session, competition)

    # First stamp R32.
    await apply_knockout_resolution(session, competition, dry_run=False)
    expected_r32 = _expected_r32_for_abcdefgh()

    # Now FINISH every R32 match. Make the HOME team win (outcome "1") so the
    # expected R16 feeders are deterministic: home of each R32 advances.
    r32_rows = (
        await session.execute(
            select(Fixture).where(Fixture.stage == "round_of_32")
        )
    ).scalars().all()
    r32_winner_by_match: dict[int, str] = {}
    for f in r32_rows:
        mn = MATCH_NUMBER_BY_EXTERNAL_ID[f.external_id]
        f.status = MatchStatus.FINISHED
        session.add(
            Score(fixture=f, home_score=2, away_score=1, source=ScoreSource.API)
        )
        r32_winner_by_match[mn] = f.home_team  # home wins
    await session.commit()

    report = await apply_knockout_resolution(session, competition, dry_run=False)

    # R16 rows should now be stamped: home=winner(feeder_home), away=winner(feeder_away).
    r16_rows = {
        MATCH_NUMBER_BY_EXTERNAL_ID[f.external_id]: f
        for f in (
            await session.execute(
                select(Fixture).where(Fixture.stage == "round_of_16")
            )
        ).scalars().all()
    }
    assert set(r16_rows.keys()) == set(range(89, 97))
    for mn, (fh, fa) in R16_FEEDS.items():
        expected_home = r32_winner_by_match[fh]
        expected_away = r32_winner_by_match[fa]
        assert (r16_rows[mn].home_team, r16_rows[mn].away_team) == (
            expected_home,
            expected_away,
        ), f"R16 match {mn} mismatch"
        assert r16_rows[mn].match_number == mn

    # Sanity: the R16 home teams are exactly the R32 home teams of the feeders,
    # which trace back to the golden R32 table.
    assert r16_rows[89].home_team == expected_r32[74][0]  # winner of 74 = home of 74


async def test_no_op_when_no_competition_rows(session, competition) -> None:
    """No knockout rows at all → empty report, no error."""
    await _seed_finished_groups(session, competition)
    report = await apply_knockout_resolution(session, competition, dry_run=False)
    assert report.changed_count == 0
    # R32 still computed in the matchup table even with no rows to stamp.
    assert report.r32_resolved is True
    assert set(range(73, 89)).issubset(set(report.matchups.keys()))

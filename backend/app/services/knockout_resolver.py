"""Knockout bracket resolver — stamp real team names onto the placeholder
knockout Fixture rows once group results (and later-round results) are in.

Why this exists
---------------
When fixtures are seeded from Football-Data, the 32 knockout rows have
placeholder team names like ``slot:round_of_32:537417:home`` (rendered
"TBD") because the real matchups aren't known until the group stage ends.
This module computes the REAL matchups from ACTUAL group standings using the
official FIFA 2026 bracket routing, and stamps the real team names (plus the
FIFA ``match_number``) onto the existing rows — keyed by the stable
Football-Data ``external_id`` and preserving each row's ``kickoff``.

R32 (matches 73-88) is computed from final group standings; R16→Final
(89-104) are filled progressively as each prior round's actual results land.

Parity with the frontend
-------------------------
The frontend computes the same matchups in
``frontend/src/lib/utils/bracketResolver.ts`` +
``frontend/src/lib/config/bracketConfig.ts`` +
``frontend/src/lib/config/thirdPlaceMapping.json``. The structural constants
below (``R32_SEEDS``, ``THIRD_SLOT_KEY``, the feeder maps) are a verified
Python port of that config — the same port already used by
``scripts/ghost_lib.py``. The third-place allocation grid is loaded from the
committed JSON (``scripts/data/third_place_mapping.json``, byte-identical to
the frontend ``thirdPlaceMapping.json``). For identical standings, the R32
matchups produced here are identical to the frontend's.

The standings themselves (incl. FIFA Article 13 tiebreakers and the
qualifying-third-place selection) come from ``app.services.standings`` — the
exact same code the frontend mirrors via the shared golden-parity tests. So
backend R32 == frontend R32 for the same group results.

external_id ↔ FIFA match_number map
-----------------------------------
``MATCH_NUMBER_BY_EXTERNAL_ID`` maps each Football-Data knockout id to its
FIFA match number (73-104). It was derived by reconciling the FD-cache
kickoffs (``backend/data/wc2026_fixtures.json``) with the official published
2026 World Cup knockout schedule (match number → date/UTC kickoff, from the
Wikipedia "2026 FIFA World Cup knockout stage" page). Every knockout kickoff
in the FD cache is distinct, so the join is a clean bijection (verified: all
32 ids map to distinct match numbers covering 73-104, no collisions). The
anchors confirm it: 537390→104 (Final), 537389→103 (3rd place),
537387→101 / 537388→102 (semi-finals).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.services.standings import (
    get_actual_group_standings,
    get_group_completion,
    get_qualifying_third_place_teams,
)

# ---------------------------------------------------------------------------
# external_id ↔ FIFA match number
# ---------------------------------------------------------------------------
#
# Derivation (see module docstring): join FD-cache kickoffs to the official
# published match-number→UTC-kickoff schedule. The map below is the verified
# result. The LAST_32 ids (537415-537430) do NOT increase with match number —
# FD assigns ids in its own order — which is exactly why this explicit map is
# required rather than sorting by id. The LAST_16-FINAL ids (537375-537390)
# happen to be in match-number order, but we still pin them explicitly.
MATCH_NUMBER_BY_EXTERNAL_ID: dict[str, int] = {
    # Round of 32 (FD LAST_32, ids 537415-537430 → FIFA 73-88)
    "537417": 73,
    "537415": 74,
    "537418": 75,
    "537423": 76,
    "537416": 77,
    "537424": 78,
    "537425": 79,
    "537426": 80,
    "537421": 81,
    "537422": 82,
    "537419": 83,
    "537420": 84,
    "537429": 85,
    "537427": 86,
    "537430": 87,
    "537428": 88,
    # Round of 16 (FD LAST_16, ids 537375-537382 → FIFA 89-96)
    "537375": 89,
    "537376": 90,
    "537377": 91,
    "537378": 92,
    "537379": 93,
    "537380": 94,
    "537381": 95,
    "537382": 96,
    # Quarter-finals (FD QUARTER_FINALS, ids 537383-537386 → FIFA 97-100)
    "537383": 97,
    "537384": 98,
    "537385": 99,
    "537386": 100,
    # Semi-finals (FD SEMI_FINALS, ids 537387-537388 → FIFA 101-102)
    "537387": 101,
    "537388": 102,
    # Third place (FD THIRD_PLACE, id 537389 → FIFA 103)
    "537389": 103,
    # Final (FD FINAL, id 537390 → FIFA 104)
    "537390": 104,
}

# Inverse map, for stamping / lookups by FIFA match number.
EXTERNAL_ID_BY_MATCH_NUMBER: dict[int, str] = {
    mn: ext for ext, mn in MATCH_NUMBER_BY_EXTERNAL_ID.items()
}


# ---------------------------------------------------------------------------
# FIFA 2026 bracket structure (Python port of bracketConfig.ts)
# ---------------------------------------------------------------------------
#
# R32 matches 73-88. Each side is either a direct group position ("1A", "2B")
# or a third-place slot, denoted "T" — resolved via the allocation grid keyed
# by THIS match's winner-key (the group-winner position it is paired with,
# per bracketResolver's MATCH_TO_WINNER_KEY). Mirrors ghost_lib.R32_SEEDS.
R32_SEEDS: dict[int, tuple[str, str]] = {
    73: ("2A", "2B"),
    74: ("1E", "T"),
    75: ("1F", "2C"),
    76: ("1C", "2F"),
    77: ("1I", "T"),
    78: ("2E", "2I"),
    79: ("1A", "T"),
    80: ("1L", "T"),
    81: ("1D", "T"),
    82: ("1G", "T"),
    83: ("2K", "2L"),
    84: ("1H", "2J"),
    85: ("1B", "T"),
    86: ("1J", "2H"),
    87: ("1K", "T"),
    88: ("2D", "2G"),
}

# Third-place slot key per R32 match (== bracketResolver MATCH_TO_WINNER_KEY).
THIRD_SLOT_KEY: dict[int, str] = {
    74: "1E",
    77: "1I",
    79: "1A",
    80: "1L",
    81: "1D",
    82: "1G",
    85: "1B",
    87: "1K",
}

# Later rounds: match -> (home feeder match, away feeder match).
# Winner of the feeder advances, EXCEPT the third-place match (103) which
# takes the LOSERS of the two semi-finals. Mirrors bracketConfig ROUND_OF_16 /
# QUARTER_FINALS / SEMI_FINALS / FINAL.
R16_FEEDS: dict[int, tuple[int, int]] = {
    89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
    93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87),
}
QF_FEEDS: dict[int, tuple[int, int]] = {97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96)}
SF_FEEDS: dict[int, tuple[int, int]] = {101: (97, 98), 102: (99, 100)}
FINAL_FEEDS: dict[int, tuple[int, int]] = {104: (101, 102)}
# Third-place play-off (103) is fed by the LOSERS of the two semi-finals.
THIRD_PLACE_FEEDS: tuple[int, int] = (101, 102)

# Feeder map for every later round that advances WINNERS (89-102, 104).
WINNER_FEEDS: dict[int, tuple[int, int]] = {
    **R16_FEEDS, **QF_FEEDS, **SF_FEEDS, **FINAL_FEEDS
}

R32_MATCH_NUMBERS = tuple(range(73, 89))
ALL_KNOCKOUT_MATCH_NUMBERS = tuple(range(73, 105))


# ---------------------------------------------------------------------------
# Third-place allocation grid
# ---------------------------------------------------------------------------

def _find_third_place_mapping_path() -> Path:
    """Locate the committed third-place allocation grid JSON.

    Prefers the backend copy (scripts/data/third_place_mapping.json); falls
    back to the frontend source of truth (thirdPlaceMapping.json). Both are
    byte-identical FIFA static data. Walks up from this file so it resolves
    under any mount layout (worktree, container, repo root)."""
    candidates = (
        "scripts/data/third_place_mapping.json",
        "frontend/src/lib/config/thirdPlaceMapping.json",
    )
    cur = Path(__file__).resolve()
    for parent in [cur.parent, *cur.parents]:
        for rel in candidates:
            candidate = parent / rel
            if candidate.exists():
                return candidate
    raise FileNotFoundError(
        "third-place allocation grid not found "
        "(scripts/data/third_place_mapping.json / thirdPlaceMapping.json)"
    )


_THIRD_PLACE_MAPPING: dict[str, dict[str, str]] | None = None


def load_third_place_mapping() -> dict[str, dict[str, str]]:
    """Load and cache the C(12,8)=495-entry third-place allocation grid."""
    global _THIRD_PLACE_MAPPING
    if _THIRD_PLACE_MAPPING is None:
        with open(_find_third_place_mapping_path()) as fh:
            _THIRD_PLACE_MAPPING = json.load(fh)
    return _THIRD_PLACE_MAPPING


# ---------------------------------------------------------------------------
# Pure matchup computation
# ---------------------------------------------------------------------------

StandingsMap = dict[str, list[dict]]


def build_group_positions(standings: StandingsMap) -> dict[str, str]:
    """{'1A': 'France', '2A': 'Germany', '3A': 'Spain', '4A': ...} from
    ranked standings. Mirrors frontend buildGroupPositions."""
    positions: dict[str, str] = {}
    for group, teams in standings.items():
        for i, team in enumerate(teams):
            positions[f"{i + 1}{group}"] = team["team"]
    return positions


def compute_r32_matchups(
    standings: StandingsMap,
    qualifying_thirds: list[dict],
) -> dict[int, tuple[str, str]]:
    """Compute the Round-of-32 matchups (FIFA matches 73-88).

    Args:
        standings: ranked standings per group, {"A": [team_dict, ...], ...}.
            Each team_dict has at least 'team' and 'group' (the shape produced
            by app.services.standings).
        qualifying_thirds: the 8 qualifying third-place team dicts (each with
            'team' and 'group'), as produced by
            get_qualifying_third_place_teams.

    Returns: {match_number: (home_team, away_team)} for 73-88.

    Raises KeyError/ValueError if standings/thirds are incomplete (a slot
    can't be resolved) — callers gate on completeness before calling.
    """
    positions = build_group_positions(standings)

    third_groups = "".join(sorted(t["group"] for t in qualifying_thirds))
    grid = load_third_place_mapping().get(third_groups)
    if grid is None:
        raise ValueError(
            f"no third-place allocation grid for combination {third_groups!r}"
        )
    third_by_group = {t["group"]: t["team"] for t in qualifying_thirds}

    def resolve(spec: str, match_no: int) -> str:
        if spec == "T":
            slot_key = THIRD_SLOT_KEY[match_no]
            target = grid[slot_key]  # e.g. "3E"
            return third_by_group[target[1:]]  # group letter -> team
        return positions[spec]

    return {
        m: (resolve(home, m), resolve(away, m))
        for m, (home, away) in R32_SEEDS.items()
    }


def resolve_round_from_results(
    winners: dict[int, str],
    losers: dict[int, str],
    match_numbers: list[int],
) -> dict[int, tuple[str, str]]:
    """Compute matchups for later-round matches whose feeders are decided.

    Args:
        winners: {feeder_match_number: winning_team} for FINISHED feeders.
        losers: {feeder_match_number: losing_team} for FINISHED feeders.
        match_numbers: which later-round matches (89-104) to compute.

    Returns {match_number: (home, away)} for every requested match whose BOTH
    feeders are present in winners/losers. Matches with a missing feeder are
    omitted (not yet resolvable). The third-place play-off (103) draws on the
    LOSERS of the semi-finals; everything else on WINNERS.
    """
    out: dict[int, tuple[str, str]] = {}
    for m in match_numbers:
        if m == 103:
            fh, fa = THIRD_PLACE_FEEDS
            home = losers.get(fh)
            away = losers.get(fa)
        else:
            feeds = WINNER_FEEDS.get(m)
            if feeds is None:
                continue
            fh, fa = feeds
            home = winners.get(fh)
            away = winners.get(fa)
        if home is not None and away is not None:
            out[m] = (home, away)
    return out


# ---------------------------------------------------------------------------
# DB application
# ---------------------------------------------------------------------------


@dataclass
class StampChange:
    """One fixture row that was (or would be) stamped."""

    external_id: str
    match_number: int
    stage: str
    old_home: str
    old_away: str
    new_home: str
    new_away: str
    old_match_number: int | None


@dataclass
class ResolutionReport:
    """Outcome of an apply_knockout_resolution run."""

    dry_run: bool
    groups_complete: bool
    r32_resolved: bool
    changes: list[StampChange] = field(default_factory=list)
    # Full computed matchup table {match_number: (home, away)} for everything
    # that could be resolved this run (for preview / human verification).
    matchups: dict[int, tuple[str, str]] = field(default_factory=dict)
    # Match numbers that couldn't be resolved yet (feeders pending / no row).
    unresolved: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def changed_count(self) -> int:
        return len(self.changes)


def _all_group_fixtures_finished(stage_status_rows: list[tuple[str, MatchStatus]]) -> bool:
    """True iff there is at least one group fixture and every one is FINISHED."""
    group_statuses = [s for stage, s in stage_status_rows if stage == "group"]
    return bool(group_statuses) and all(s == MatchStatus.FINISHED for s in group_statuses)


async def apply_knockout_resolution(
    session: AsyncSession,
    competition: Competition,
    *,
    dry_run: bool = False,
) -> ResolutionReport:
    """Stamp real team names + FIFA match_number onto the knockout fixtures.

    Behaviour:
      * R32 (73-88) is stamped only when ALL group fixtures are FINISHED.
      * A later-round fixture (89-104) is stamped only when BOTH its feeder
        matches have a FINISHED Score (winner/loser resolvable). The
        third-place play-off (103) uses the semi-final LOSERS.
      * Idempotent: re-running with the same results changes nothing.
      * Never deletes rows; never touches ``kickoff`` or ``external_id``.
      * ``match_number`` is always backfilled from
        MATCH_NUMBER_BY_EXTERNAL_ID for every known knockout row, even if the
        teams aren't resolvable yet.

    With ``dry_run=True`` nothing is committed; the report still lists every
    change that WOULD be made plus the full computed matchup table.
    """
    report = ResolutionReport(
        dry_run=dry_run, groups_complete=False, r32_resolved=False
    )

    # Load all knockout fixtures for this competition, with scores eager.
    result = await session.execute(
        select(Fixture)
        .options(selectinload(Fixture.score))
        .where(
            Fixture.competition_id == competition.id,
            Fixture.stage != "group",
        )
    )
    knockout_fixtures = list(result.scalars().all())
    fixtures_by_match: dict[int, Fixture] = {}
    for fx in knockout_fixtures:
        mn = MATCH_NUMBER_BY_EXTERNAL_ID.get(fx.external_id or "")
        if mn is None:
            report.notes.append(
                f"knockout fixture {fx.external_id!r} not in match-number map; skipped"
            )
            continue
        fixtures_by_match[mn] = fx

    # Group completion gate for R32.
    status_rows = (
        await session.execute(
            select(Fixture.stage, Fixture.status).where(
                Fixture.competition_id == competition.id
            )
        )
    ).all()
    groups_complete = _all_group_fixtures_finished(status_rows)
    report.groups_complete = groups_complete

    matchups: dict[int, tuple[str, str]] = {}

    # --- R32 from final group standings ---
    if groups_complete:
        standings = await get_actual_group_standings(session)
        qualifying_thirds = await get_qualifying_third_place_teams(session)
        # Only attempt if we actually have 12 ranked groups and 8 thirds —
        # otherwise a slot would raise. get_group_completion already told us
        # every group fixture is FINISHED, so this should hold; guard anyway.
        ranked_groups = sum(1 for teams in standings.values() if len(teams) >= 3)
        if ranked_groups >= 12 and len(qualifying_thirds) >= 8:
            matchups.update(compute_r32_matchups(standings, qualifying_thirds))
            report.r32_resolved = True
        else:
            report.notes.append(
                f"groups finished but standings incomplete "
                f"(ranked_groups={ranked_groups}, thirds={len(qualifying_thirds)}); "
                f"R32 not computed"
            )

    # --- Later rounds from actual results ---
    # Collect winners/losers from FINISHED feeder matches. A feeder's
    # winner/loser come from the score's outcome property (handles ET/pens).
    winners: dict[int, str] = {}
    losers: dict[int, str] = {}
    for mn, fx in fixtures_by_match.items():
        score = fx.score
        if fx.status != MatchStatus.FINISHED or score is None:
            continue
        # A feeder is only usable if its teams are real (not placeholders).
        if _is_placeholder(fx.home_team) or _is_placeholder(fx.away_team):
            continue
        outcome = score.outcome  # "1" home, "2" away, "X" draw
        if outcome == "1":
            winners[mn], losers[mn] = fx.home_team, fx.away_team
        elif outcome == "2":
            winners[mn], losers[mn] = fx.away_team, fx.home_team
        # A draw with no ET/pens shouldn't happen in knockout; skip if so.

    later = resolve_round_from_results(
        winners, losers, list(range(89, 105))
    )
    matchups.update(later)

    report.matchups = dict(sorted(matchups.items()))

    # --- Stamp ---
    for mn in ALL_KNOCKOUT_MATCH_NUMBERS:
        fx = fixtures_by_match.get(mn)
        if fx is None:
            # No DB row for this match number — note it for later rounds only
            # if we expected to resolve it.
            if mn in matchups:
                report.notes.append(
                    f"computed match {mn} but no fixture row to stamp"
                )
            continue

        pair = matchups.get(mn)
        # Track matches whose teams still aren't resolved (placeholder), even
        # when we backfill their match_number this run — otherwise the admin
        # preview's `unresolved` list omits R32 rows that only got an mn stamp.
        if pair is None and _is_placeholder(fx.home_team):
            report.unresolved.append(mn)

        # Determine desired values.
        desired_mn = mn
        desired_home = pair[0] if pair else fx.home_team
        desired_away = pair[1] if pair else fx.away_team

        teams_changed = pair is not None and (
            fx.home_team != desired_home or fx.away_team != desired_away
        )
        mn_changed = fx.match_number != desired_mn

        if not teams_changed and not mn_changed:
            continue

        report.changes.append(
            StampChange(
                external_id=fx.external_id or "",
                match_number=mn,
                stage=fx.stage,
                old_home=fx.home_team,
                old_away=fx.away_team,
                new_home=desired_home,
                new_away=desired_away,
                old_match_number=fx.match_number,
            )
        )

        if not dry_run:
            if teams_changed:
                fx.home_team = desired_home
                fx.away_team = desired_away
            if mn_changed:
                fx.match_number = desired_mn
            fx.updated_at = utc_now()

    report.unresolved = sorted(set(report.unresolved))

    if not dry_run and report.changes:
        await session.commit()

    return report


def _is_placeholder(name: str) -> bool:
    """True for an unresolved slot placeholder like 'slot:round_of_32:537417:home'."""
    return name.startswith("slot:")

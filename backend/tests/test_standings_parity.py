"""Cross-language parity for the FIFA WC2026 Article 13 tiebreaker.

This is the backend half of a two-language guarantee: the SAME golden cases in
`shared/standings-parity-cases.json` are also run by the frontend Vitest suite
(`frontend/src/lib/utils/standings.parity.test.ts`). Both implementations must
produce the identical ranked order + warnings for every case. If the backend
`standings.py` and the frontend `standings.ts` ever drift, one of these two
suites fails — which is the whole reason the file exists.

See `feedback_frontend_backend_logic_parity` in memory and CLAUDE.md's
"Scoring Engine Safety" rule: duplicated domain logic is changed on both sides
together, locked by these cases.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.standings import _apply_fifa_tiebreakers, build_and_rank_group


def _find_file(relative: str) -> Path | None:
    """Walk up from this test file looking for `relative`. Same pattern as
    test_third_place_mapping.py — robust to the varying mount layouts the
    backend tests run under (container vs host, main repo vs worktree)."""
    cur = Path(__file__).resolve()
    for parent in [cur.parent, *cur.parents]:
        candidate = parent / relative
        if candidate.exists():
            return candidate
    return None


_CASES_FILE = _find_file("shared/standings-parity-cases.json")


def _load_cases() -> list[dict]:
    assert _CASES_FILE is not None, (
        "shared/standings-parity-cases.json not found via parent-walk. In the "
        "backend container it must be mounted (see docker-compose.yml: "
        "'./shared:/app/shared:ro')."
    )
    return json.loads(_CASES_FILE.read_text())["cases"]


def _normalize_warnings(warnings: list) -> list[tuple]:
    """Reduce warnings to the (sorted tied_teams, context) pairs we assert on.
    `group` is intentionally ignored — it's ambiguous for cross-group ties."""
    return sorted(
        (tuple(sorted(w["tied_teams"])), w["context"]) for w in warnings
    )


def _expected_warnings(case: dict) -> list[tuple]:
    return sorted(
        (tuple(sorted(w["tied_teams"])), w["context"])
        for w in case.get("expected_warnings", [])
    )


def _run_case(case: dict) -> tuple[list[str], list[tuple]]:
    """Execute one parity case through the production ranking code and return
    (ordered team names, normalized warnings)."""
    rankings = case.get("fifa_rankings", [])

    if case["context"] == "group_standings":
        # Build duck-typed (fixture, score) tuples — build_and_rank_group only
        # reads .home_team/.away_team and .home_score/.away_score.
        matches = [
            (
                SimpleNamespace(home_team=m["home"], away_team=m["away"], group=case["group"]),
                SimpleNamespace(home_score=m["home_score"], away_score=m["away_score"]),
            )
            for m in case["matches"]
        ]
        sorted_teams, warnings = build_and_rank_group(
            matches, case["group"], fifa_rankings=rankings
        )
    else:  # third_place_qualifying — pre-aggregated, H2H not applicable.
        teams = [
            {
                "team": t["team"],
                "group": t["group"],
                "points": t["points"],
                "goal_difference": t["gd"],
                "goals_for": t["gf"],
            }
            for t in case["teams"]
        ]
        sorted_teams, warnings = _apply_fifa_tiebreakers(
            teams,
            group_matches=None,
            context="third_place_qualifying",
            fifa_rankings=rankings,
        )

    return [t["team"] for t in sorted_teams], _normalize_warnings(warnings)


def test_parity_cases_file_is_available() -> None:
    """Guard: the golden fixture must be present/mounted, else parity is untested."""
    assert _CASES_FILE is not None and _CASES_FILE.exists(), (
        "shared/standings-parity-cases.json missing — restore it or remount "
        "the ./shared volume. Without it the frontend/backend tiebreaker "
        "implementations are no longer pinned to agree."
    )


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_standings_parity(case: dict) -> None:
    order, warnings = _run_case(case)
    assert order == case["expected_order"], (
        f"[{case['name']}] order mismatch:\n"
        f"  expected: {case['expected_order']}\n"
        f"  actual:   {order}"
    )
    assert warnings == _expected_warnings(case), (
        f"[{case['name']}] warning mismatch:\n"
        f"  expected: {_expected_warnings(case)}\n"
        f"  actual:   {warnings}"
    )

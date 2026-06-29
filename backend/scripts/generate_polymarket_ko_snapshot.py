"""Generate scripts/data/polymarket_ko_wc2026.json — the Polymarket ghost's
PHASE-2 (knockout) input.

Companion to generate_polymarket_snapshot.py (which froze the pre-tournament
group snapshot). This one reads the LATEST snapshot in the prediction-model
DuckDB — i.e. the live knockout odds you just scraped with
`prediction-model/scripts/refresh_market.py` — and emits, for the KO matches
that currently have tradeable two-sided books:

  - match_scores: most-likely exact score per live KO matchup (modal OUTCOME
    from the 1X2 mids, then the highest-MID two-sided concrete scoreline within
    that outcome; same rule as the group snapshot).
  - team_stage_probs: raw reach-market mids per team, keyed by our stage names
    — drives the Phase-2 bracket re-pick support.

Runs on the ANALYSIS MACHINE (needs DuckDB), NOT in the backend container:

    ~/pyfiles/prediction-model/.venv/bin/python \
        backend/scripts/generate_polymarket_ko_snapshot.py

The committed JSON is what scripts/seed_ghosts_ko.py consumes, so prod never
needs DuckDB or Polymarket access.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

DB = Path.home() / "pyfiles" / "prediction-model" / "data" / "analytics.duckdb"
OUT = Path(__file__).parent / "data" / "polymarket_ko_wc2026.json"

STAGE_BY_MARKET_TYPE = {
    "R32": "round_of_32",
    "R16": "round_of_16",
    "QF": "quarter_final",
    "SF": "semi_final",
    "FINAL": "final",
    "champion": "winner",
}

FALLBACK_SCORE = {"home": (2, 1), "draw": (1, 1), "away": (1, 2)}


def _side(h: int, a: int) -> str:
    return "home" if h > a else "away" if a > h else "draw"


def match_scores(con, snap) -> list[dict]:
    """Modal-outcome → best two-sided scoreline, for the LATEST snapshot's
    live KO matchups only."""
    outcomes = con.execute(
        "select home, away, outcome, prob_raw from polymarket_match_1x2 "
        "where snapshot_at = ?",
        [snap],
    ).fetchall()
    fav: dict[tuple[str, str], str] = {}
    best: dict[tuple[str, str], float] = {}
    for home, away, outcome, p in outcomes:
        key = (home, away)
        if p is not None and p > best.get(key, -1):
            best[key] = p
            fav[key] = outcome

    grid = con.execute(
        "select home, away, score_home, score_away, best_bid, best_ask "
        "from polymarket_match_score "
        "where snapshot_at = ? and is_other = false and score_home is not null",
        [snap],
    ).fetchall()
    by_match: dict[tuple[str, str], list[tuple[float, int, int]]] = {}
    for home, away, sh, sa, bid, ask in grid:
        if bid is None or ask is None or bid <= 0:  # two-sided books only
            continue
        mid = (bid + ask) / 2
        by_match.setdefault((home, away), []).append((mid, int(sh), int(sa)))

    fallbacks = 0
    rows = []
    for key, outcome in sorted(fav.items()):
        home, away = key
        candidates = [
            (p, h, a) for p, h, a in by_match.get(key, []) if _side(h, a) == outcome
        ]
        if candidates:
            _, h, a = max(candidates, key=lambda c: (c[0], -(c[1] + c[2]), -c[1]))
        else:
            fallbacks += 1
            h, a = FALLBACK_SCORE[outcome]
        rows.append({"home": home, "away": away, "score": [h, a]})
    print(f"  {len(rows)} KO matchups ({fallbacks} used a fallback scoreline)")
    return rows


def team_stage_probs(con, snap) -> dict[str, dict[str, float]]:
    rows = con.execute(
        "select team, market_type, prob_raw from polymarket_team_odds "
        "where snapshot_at = ?",
        [snap],
    ).fetchall()
    out: dict[str, dict[str, float]] = {}
    for team, mtype, p in rows:
        stage = STAGE_BY_MARKET_TYPE.get(mtype)
        if stage is None:  # win_group not used
            continue
        out.setdefault(team, {})[stage] = float(p or 0.0)
    return out


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    snap = con.execute("select max(snapshot_at) from polymarket_match_1x2").fetchone()[0]
    print(f"latest snapshot: {snap}")
    scores = match_scores(con, snap)
    probs = team_stage_probs(con, snap)
    if not scores:
        raise SystemExit("no KO matchups in the latest snapshot — re-run refresh_market.py")

    OUT.write_text(
        json.dumps(
            {
                "snapshot_at": str(snap),
                "match_scores": scores,
                "team_stage_probs": probs,
            },
            indent=1,
            ensure_ascii=False,
        )
    )
    print(f"wrote {OUT} ({len(scores)} matchups, {len(probs)} teams)")


if __name__ == "__main__":
    main()

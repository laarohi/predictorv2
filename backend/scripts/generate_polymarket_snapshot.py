"""Generate scripts/data/polymarket_wc2026.json — the Polymarket ghost's input.

Runs on the ANALYSIS MACHINE, not in the backend container: it reads the
prediction-model's DuckDB (the June-9 pre-tournament Polymarket snapshot)
and scrapes the four player-award markets from the public Gamma API. The
committed JSON is what scripts/seed_ghosts.py consumes, so prod never
needs DuckDB or network access to Polymarket.

    ~/pyfiles/prediction-model/.venv/bin/python \
        backend/scripts/generate_polymarket_snapshot.py

Selection rules (mirrors the crowd ghost's outcome-first logic):
- per match: modal OUTCOME from the 1X2 mids (those markets are liquid),
  then the highest-MID concrete scoreline within that outcome — counting
  ONLY two-sided books (real bid AND ask). Exact-score markets are
  mostly untraded; an ask-only book yields yes_price = ask/2, which once
  produced garbage like "Cape Verde 3-0 Saudi Arabia at 0.435" and a
  wall of 3-0 picks. If no two-sided scoreline exists for the favoured
  outcome, fall back to 2-1 / 1-1 / 1-2.
- team_stage_probs: raw mids per reach market, keyed by our stage names.
- award_answers: top yes-price outcome of each award market.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

import duckdb

DB = Path.home() / "pyfiles" / "prediction-model" / "data" / "analytics.duckdb"
OUT = Path(__file__).parent / "data" / "polymarket_wc2026.json"

STAGE_BY_MARKET_TYPE = {
    "R32": "round_of_32",
    "R16": "round_of_16",
    "QF": "quarter_final",
    "SF": "semi_final",
    "FINAL": "final",
    "champion": "winner",
}

# Gamma event slug -> our bonus question id.
AWARD_EVENTS = {
    "world-cup-golden-ball-winner-20260603194031758": "best_player",
    "world-cup-golden-boot-winner": "top_scorer",
    "world-cup-young-player-award-winner-20260602160649063": "best_young_player",
    "world-cup-golden-glove-winner-20260603195306910": "golden_glove",
}

FALLBACK_SCORE = {"home": (2, 1), "draw": (1, 1), "away": (1, 2)}


def match_scores(con) -> list[dict]:
    outcomes = con.execute(
        "select home, away, outcome, prob_raw from polymarket_match_1x2"
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
        "where is_other = false and score_home is not null"
    ).fetchall()
    by_match: dict[tuple[str, str], list[tuple[float, int, int]]] = {}
    for home, away, sh, sa, bid, ask in grid:
        # Two-sided books only — see module docstring for the ask-only trap.
        if bid is None or ask is None or bid <= 0:
            continue
        mid = (bid + ask) / 2
        by_match.setdefault((home, away), []).append((mid, int(sh), int(sa)))

    fallbacks = 0
    rows = []
    for key, outcome in sorted(fav.items()):
        home, away = key
        side = lambda h, a: "home" if h > a else "away" if a > h else "draw"  # noqa: E731
        candidates = [
            (p, h, a) for p, h, a in by_match.get(key, []) if side(h, a) == outcome
        ]
        if candidates:
            # max mid; ties -> fewer goals, lower home score.
            _, h, a = max(candidates, key=lambda c: (c[0], -(c[1] + c[2]), -c[1]))
        else:
            fallbacks += 1
            h, a = FALLBACK_SCORE[outcome]
        rows.append({"home": home, "away": away, "score": [h, a]})
    print(f"  {fallbacks} matches had no two-sided scoreline (fallback used)")
    return rows


def team_stage_probs(con) -> dict[str, dict[str, float]]:
    rows = con.execute(
        "select team, market_type, prob_raw from polymarket_team_odds"
    ).fetchall()
    out: dict[str, dict[str, float]] = {}
    for team, mtype, p in rows:
        stage = STAGE_BY_MARKET_TYPE.get(mtype)
        if stage is None:  # win_group not used
            continue
        out.setdefault(team, {})[stage] = float(p or 0.0)
    return out


def award_answers() -> dict[str, str]:
    answers = {}
    for slug, qid in AWARD_EVENTS.items():
        req = urllib.request.Request(
            f"https://gamma-api.polymarket.com/events?slug={slug}",
            headers={
                # Gamma 403s the default urllib agent.
                "User-Agent": "Mozilla/5.0 (predictor-ghost-snapshot)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req) as resp:
            events = json.load(resp)
        if not events:
            raise SystemExit(f"award event not found: {slug}")
        candidates = []
        for m in events[0]["markets"]:
            name = (m.get("groupItemTitle") or m["question"]).strip()
            # Skip the untraded "Player A".."Player Z" template slots and
            # the catch-all bucket — only real, traded player outcomes.
            if re.fullmatch(r"Player [A-Z]{1,2}", name) or name == "Other":
                continue
            volume = float(m.get("volumeNum") or 0)
            if volume <= 0:
                continue
            try:
                yes = float(json.loads(m["outcomePrices"])[0])
            except (KeyError, ValueError, TypeError):
                continue
            candidates.append((yes, volume, name))
        if not candidates:
            raise SystemExit(f"no traded player outcomes for {slug}")
        top_yes, _, top_name = max(candidates)
        answers[qid] = top_name
        print(f"  {qid}: {top_name} ({top_yes:.3f})")
    return answers


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    snapshot_at = con.execute(
        "select max(snapshot_at) from polymarket_team_odds"
    ).fetchone()[0]
    scores = match_scores(con)
    probs = team_stage_probs(con)
    assert len(scores) == 72, f"expected 72 matches, got {len(scores)}"
    assert len(probs) == 48, f"expected 48 teams, got {len(probs)}"

    print("award markets (live scrape):")
    awards = award_answers()

    OUT.write_text(
        json.dumps(
            {
                "snapshot_at": str(snapshot_at),
                "match_scores": scores,
                "team_stage_probs": probs,
                "award_answers": awards,
            },
            indent=1,
            ensure_ascii=False,
        )
    )
    print(f"wrote {OUT} ({len(scores)} matches, {len(probs)} teams)")


if __name__ == "__main__":
    main()

"""Deterministic knockout split from ESPN's summary `linescores`
(espn.parse_summary_split).

ESPN's live scoreboard reports ONE running total and, during a shootout, was
observed folding the penalty goals into that total — so freezing the live score
corrupts the 90' value (WC2026 R32: Germany 1-1 Paraguay, 3-4 pens, stored as
"everything added together"). The summary endpoint instead exposes per-period
`linescores` — [H1, H2, ET1, ET2, shootout] — from which 90' (P1+P2), the
after-ET total (all play periods) and the shootout are all read deterministically,
independent of polling timing. This locks that contract.
"""

from app.services.external.espn import KnockoutSplit, parse_summary_split


def _summary(home_ls, away_ls, *, home_score, away_score, home_pen=None, away_pen=None):
    """Build a minimal ESPN summary payload with the fields the parser reads."""

    def competitor(side, linescores, score, pen):
        c = {
            "homeAway": side,
            "score": str(score),
            "linescores": [{"displayValue": str(v)} for v in linescores],
        }
        if pen is not None:
            c["shootoutScore"] = pen
        return c

    return {
        "header": {
            "competitions": [
                {
                    "competitors": [
                        competitor("home", home_ls, home_score, home_pen),
                        competitor("away", away_ls, away_score, away_pen),
                    ]
                }
            ]
        }
    }


def test_real_shootout_germany_paraguay():
    # The exact R32 payload: 1-1 at 90', 1-1 after ET, 3-4 on penalties.
    summary = _summary(
        [0, 1, 0, 0, 3], [1, 0, 0, 0, 4],
        home_score=1, away_score=1, home_pen=3, away_pen=4,
    )
    assert parse_summary_split(summary) == KnockoutSplit(1, 1, 1, 1, 3, 4)


def test_extra_time_winner_no_shootout():
    # 1-1 at 90', a 2-1 winner in extra time, no shootout. The 90' split (1-1)
    # is recovered even though the after-ET total (2-1) differs — the case the
    # old running-total freeze could mis-capture.
    summary = _summary(
        [1, 0, 1, 0], [0, 1, 0, 0],
        home_score=2, away_score=1,
    )
    assert parse_summary_split(summary) == KnockoutSplit(1, 1, 2, 1, None, None)


def test_regulation_only_two_periods():
    # A match decided in 90' — two linescores, no ET, no pens.
    summary = _summary([2, 0], [0, 1], home_score=2, away_score=1)
    assert parse_summary_split(summary) == KnockoutSplit(2, 1, None, None, None, None)


def test_shootout_score_as_float_is_accepted():
    # The summary endpoint reports shootoutScore as a float (3.0); still fine.
    summary = _summary(
        [0, 1, 0, 0, 3], [1, 0, 0, 0, 4],
        home_score=1, away_score=1, home_pen=3.0, away_pen=4.0,
    )
    assert parse_summary_split(summary) == KnockoutSplit(1, 1, 1, 1, 3, 4)


def test_undecided_shootout_returns_none():
    # Equal penalties = a shootout still in progress. Refuse it so we never
    # finalize / notify mid-shootout (the "4-4 pens" completion-push bug).
    summary = _summary(
        [0, 1, 0, 0, 4], [1, 0, 0, 0, 4],
        home_score=1, away_score=1, home_pen=4, away_pen=4,
    )
    assert parse_summary_split(summary) is None


def test_aet_total_mismatch_returns_none():
    # Linescores sum to a different after-ET total than the reported `score`
    # (mid-update / inconsistent) — bail out and let the freeze fall back.
    summary = _summary(
        [0, 1, 0, 0, 3], [1, 0, 0, 0, 4],
        home_score=5, away_score=1, home_pen=3, away_pen=4,
    )
    assert parse_summary_split(summary) is None


def test_shootout_linescore_disagrees_with_shootoutscore_returns_none():
    # Last linescore (3) != reported shootoutScore (5): structural surprise.
    summary = _summary(
        [0, 1, 0, 0, 3], [1, 0, 0, 0, 4],
        home_score=1, away_score=1, home_pen=5, away_pen=4,
    )
    assert parse_summary_split(summary) is None


def test_shootout_on_one_side_only_returns_none():
    summary = _summary(
        [0, 1, 0, 0, 3], [1, 0, 0, 0, 4],
        home_score=1, away_score=1, home_pen=3, away_pen=None,
    )
    assert parse_summary_split(summary) is None


def test_missing_linescores_returns_none():
    summary = {
        "header": {
            "competitions": [
                {
                    "competitors": [
                        {"homeAway": "home", "score": "1"},
                        {"homeAway": "away", "score": "1"},
                    ]
                }
            ]
        }
    }
    assert parse_summary_split(summary) is None


def test_empty_payload_returns_none():
    assert parse_summary_split({}) is None
    assert parse_summary_split({"header": {}}) is None

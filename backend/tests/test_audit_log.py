"""Unit tests for the audit-log formatter functions.

Covers the public-facing prettifiers in `app.services.audit_log` —
parse_user_agent and the three private _format_* helpers, exercised
indirectly via fake history rows.
"""

from app.models.prediction_history import PredictionAction
from app.services.audit_log import (
    _format_bonus_change,
    _format_match_change,
    _format_team_change,
    parse_user_agent,
)


class TestParseUserAgent:
    """UA → friendly device summary."""

    def test_iphone_safari(self):
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        assert parse_user_agent(ua) == "iPhone Safari"

    def test_android_chrome(self):
        ua = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537 (KHTML, like Gecko) Chrome/120 Mobile Safari/537"
        assert parse_user_agent(ua) == "Android Chrome"

    def test_mac_chrome(self):
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537 (KHTML, like Gecko) Chrome/120 Safari/537"
        assert parse_user_agent(ua) == "Mac Chrome"

    def test_windows_firefox(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
        assert parse_user_agent(ua) == "Windows Firefox"

    def test_mac_safari(self):
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        assert parse_user_agent(ua) == "Mac Safari"

    def test_edge_on_windows(self):
        ua = "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537 (KHTML, like Gecko) Chrome/120 Safari/537 Edg/120"
        assert parse_user_agent(ua) == "Windows Edge"

    def test_curl(self):
        assert parse_user_agent("curl/8.4.0") == "Unknown device (API client)"

    def test_empty_ua(self):
        assert parse_user_agent("") == "Unknown"
        assert parse_user_agent(None) == "Unknown"


class TestFormatMatchChange:
    """Score diff renderer."""

    def test_insert(self):
        assert _format_match_change(
            "Brazil", "Germany", None,
            {"home_score": 2, "away_score": 1, "phase": "phase_1"},
            PredictionAction.INSERT,
        ) == "Brazil 2-1 Germany"

    def test_update(self):
        assert _format_match_change(
            "Brazil", "Germany",
            {"home_score": 2, "away_score": 1},
            {"home_score": 3, "away_score": 0},
            PredictionAction.UPDATE,
        ) == "Brazil 2-1 → 3-0 Germany"

    def test_lock(self):
        assert _format_match_change(
            "Brazil", "Germany",
            {"home_score": 2, "away_score": 1},
            {"home_score": 2, "away_score": 1, "locked_at": "2026-06-11T14:32:00Z"},
            PredictionAction.LOCK,
        ) == "Locked: Brazil 2-1 Germany"


class TestFormatTeamChange:
    """Bracket pick renderer."""

    def test_insert(self):
        assert _format_team_change(
            "Argentina", "final", None,
            {"team": "Argentina", "stage": "final"},
            PredictionAction.INSERT,
        ) == "Final: added Argentina"

    def test_delete(self):
        assert _format_team_change(
            "Brazil", "semi_final",
            {"team": "Brazil", "stage": "semi_final"}, None,
            PredictionAction.DELETE,
        ) == "Semi-finals: removed Brazil"

    def test_stage_label_pretty(self):
        # round_of_16 → "Round of 16"
        assert _format_team_change(
            "France", "round_of_16", None,
            {"team": "France", "stage": "round_of_16"},
            PredictionAction.INSERT,
        ) == "Round of 16: added France"


class TestFormatBonusChange:
    """Bonus pick renderer."""

    def test_insert(self):
        assert _format_bonus_change(
            "Golden Boot — top scorer",
            None, {"answer": "Lamine Yamal"},
            PredictionAction.INSERT,
        ) == "Golden Boot — top scorer: Lamine Yamal"

    def test_update(self):
        assert _format_bonus_change(
            "Golden Boot — top scorer",
            {"answer": "Vinicius Jr"},
            {"answer": "Lamine Yamal"},
            PredictionAction.UPDATE,
        ) == "Golden Boot — top scorer: Vinicius Jr → Lamine Yamal"

    def test_delete(self):
        assert _format_bonus_change(
            "Golden Boot — top scorer",
            {"answer": "Vinicius Jr"}, None,
            PredictionAction.DELETE,
        ) == "Golden Boot — top scorer: cleared (was Vinicius Jr)"

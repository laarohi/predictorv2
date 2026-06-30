"""ESPN public scoreboard client — unofficial JSON API, no auth required.

Primary LIVE score source: ESPN's site API updates in-play scores in near
real time, while Football-Data.org's free tier delivers them with a delay.
The endpoint is the same one every espn.com browser tab polls, so our one
request per minute during match windows is negligible traffic.

Role split (see external_scores.get_score_provider): ESPN paints live
scores and emits completed matches as non-authoritative finals — enough to
finish a group-stage fixture instantly. Knockout finals still land via
Football-Data's per-fixture resolution pass, which carries the
authoritative FT/ET/penalties split our scoring expects.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.models.fixture import MatchStatus

logger = logging.getLogger(__name__)


class EspnError(Exception):
    """Catch-all for ESPN HTTP / parsing failures."""


BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# Soccer regulation is two halves. ESPN numbers periods 1=H1, 2=H2, then
# 3=ET1, 4=ET2, 5=shootout — so the first REGULATION_PERIODS linescores sum
# to the 90-minute score, and the shootout is the final linescore entry.
REGULATION_PERIODS = 2

# status.type.name substrings that mean a knockout has gone past 90 minutes
# (live ET, live shootout, or a finished-after-ET/penalties final). Substring
# matching is deliberately loose — ESPN's exact in-play ET/shootout status
# names are not contractually stable, but all of them carry one of these.
_PAST_REGULATION_STATUS_MARKERS = ("EXTRA", "OVERTIME", "SHOOTOUT", "PEN", "AET")

# Our competition rows store Football-Data codes ("WC"); map them to ESPN
# league slugs. Unknown codes fall back to the World Cup slug.
LEAGUE_SLUGS = {"WC": "fifa.world"}

# ESPN display names that differ from our canonical (Football-Data-seeded)
# fixture team names. Verified 2026-06-10 by diffing the full tournament
# scoreboard against the fixtures table — these were the only two of 48.
TEAM_NAME_ALIASES = {
    "Cape Verde": "Cape Verde Islands",
    "Türkiye": "Turkey",
}

# status.type.name overrides; anything else is decided by status.type.state
# (pre → SCHEDULED, in → LIVE, post+completed → FINISHED).
_STATUS_NAME_MAP = {
    "STATUS_HALFTIME": MatchStatus.HALFTIME,
}


def map_event_status(status_type: dict[str, Any]) -> MatchStatus | None:
    """Map ESPN's status.type to our MatchStatus.

    'post' states map to FINISHED only when ESPN flags the event as
    completed (a played-out match); abandoned/postponed/cancelled events
    carry completed=False and return None so they never touch a fixture.
    """
    name = status_type.get("name", "")
    state = status_type.get("state", "")
    if state == "post":
        return MatchStatus.FINISHED if status_type.get("completed") else None
    if name in _STATUS_NAME_MAP:
        return _STATUS_NAME_MAP[name]
    if state == "in":
        return MatchStatus.LIVE
    return MatchStatus.SCHEDULED


def parse_minute(display_clock: str | None) -> int | None:
    """'45'' → 45, '90'+3'' → 90, garbage/empty → None."""
    if not display_clock:
        return None
    m = re.match(r"(\d+)", display_clock)
    return int(m.group(1)) if m else None


def canonical_team_name(espn_name: str) -> str:
    return TEAM_NAME_ALIASES.get(espn_name, espn_name)


@dataclass
class KnockoutSplit:
    """A knockout match's score broken into its three scoring phases, read
    deterministically from ESPN's summary `linescores` (one goal tally per
    period) rather than a live running total.

    - reg  = score after 90 minutes (sum of the regulation periods)
    - et   = score after extra time (all play periods); None if the match
             ended in regulation
    - pen  = shootout result; None if there was no shootout

    This is the authoritative replacement for the score_sync "freeze": it does
    not depend on catching a particular live tick, and ESPN folding shootout
    goals into the live `score` field can no longer corrupt the 90' value.
    """

    home_reg: int
    away_reg: int
    home_et: int | None
    away_et: int | None
    home_pen: int | None
    away_pen: int | None


def _linescore_int(entry: Any) -> int:
    """One ESPN linescores entry → int. Prefers displayValue ('3'), falls back
    to the numeric value (3.0). Raises ValueError on anything else so the
    caller treats the whole summary as untrustworthy."""
    if isinstance(entry, dict):
        dv = entry.get("displayValue")
        if dv is not None:
            return int(str(dv))
        val = entry.get("value")
        if val is not None:
            return int(val)
    raise ValueError(f"unparseable linescore entry: {entry!r}")


def _parse_side(competitor: dict[str, Any]) -> dict[str, Any] | None:
    """Parse one competitor's per-period split. Returns a dict with reg/et/pen
    and the cross-check fields (the reported AET `score` and `shootoutScore`),
    or None if the linescores are missing/malformed."""
    raw = competitor.get("linescores")
    if not isinstance(raw, list) or len(raw) < REGULATION_PERIODS:
        return None
    try:
        vals = [_linescore_int(e) for e in raw]
    except (ValueError, TypeError):
        return None
    if any(v < 0 for v in vals):
        return None

    shootout = competitor.get("shootoutScore")
    has_pen = shootout is not None
    if has_pen:
        # Shootout games carry the pens as the final linescore on top of the
        # (always present) regulation + ET periods.
        if len(vals) <= REGULATION_PERIODS:
            return None
        pen = vals[-1]
        play = vals[:-1]
    else:
        pen = None
        play = vals

    if len(play) < REGULATION_PERIODS:
        return None

    reg = sum(play[:REGULATION_PERIODS])
    went_past_regulation = has_pen or len(play) > REGULATION_PERIODS
    et = sum(play) if went_past_regulation else None

    score_total = None
    raw_score = competitor.get("score")
    if raw_score is not None:
        try:
            score_total = int(str(raw_score))
        except (ValueError, TypeError):
            return None

    pen_reported = None
    if has_pen:
        try:
            pen_reported = int(shootout)
        except (ValueError, TypeError):
            return None

    return {"reg": reg, "et": et, "pen": pen,
            "score_total": score_total, "pen_reported": pen_reported}


def parse_summary_split(summary: dict[str, Any]) -> KnockoutSplit | None:
    """Extract a deterministic KnockoutSplit from an ESPN event-summary payload.

    Returns None — signalling the caller to fall back — whenever the data is
    missing, malformed, internally inconsistent, or describes a shootout that
    has not yet been decided (equal penalties). Never raises; never guesses.
    """
    try:
        comp = summary["header"]["competitions"][0]
        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    except (KeyError, IndexError, TypeError):
        return None

    home_c, away_c = sides.get("home"), sides.get("away")
    if not home_c or not away_c:
        return None

    home, away = _parse_side(home_c), _parse_side(away_c)
    if home is None or away is None:
        return None

    # A shootout must be present on both sides or neither.
    if (home["pen"] is None) != (away["pen"] is None):
        return None

    if home["pen"] is not None:
        # An undecided shootout (equal pens) is not a final result — refuse it
        # so we never finalize/notify mid-shootout.
        if home["pen"] == away["pen"]:
            return None
        # The shootout linescore must agree with the reported shootoutScore.
        if home["pen"] != home["pen_reported"] or away["pen"] != away["pen_reported"]:
            return None

    # The summed play periods (the AET total) must agree with ESPN's reported
    # `score`; a mismatch means the linescores are mid-update / inconsistent.
    for side in (home, away):
        if side["et"] is not None and side["score_total"] is not None and side["et"] != side["score_total"]:
            return None

    return KnockoutSplit(
        home_reg=home["reg"], away_reg=away["reg"],
        home_et=home["et"], away_et=away["et"],
        home_pen=home["pen"], away_pen=away["pen"],
    )


def competition_past_regulation(competition: dict[str, Any]) -> bool:
    """True if a scoreboard competition shows a knockout that has reached or
    passed extra time / a shootout — the cue to fetch the summary for a clean
    split. Group matches never trip this (no ET, no shootoutScore)."""
    competitors = competition.get("competitors", []) or []
    if any(c.get("shootoutScore") is not None for c in competitors):
        return True
    status = competition.get("status", {}) or {}
    period = status.get("period")
    if isinstance(period, (int, float)) and period > REGULATION_PERIODS:
        return True
    name = (status.get("type", {}) or {}).get("name", "") or ""
    return any(marker in name for marker in _PAST_REGULATION_STATUS_MARKERS)


class EspnClient:
    """Thin async wrapper over the scoreboard endpoint with light retries."""

    DEFAULT_TIMEOUT = 10.0
    MAX_RETRIES = 2
    BACKOFF_SECONDS = (1.0,)

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    async def get_scoreboard(self, league_slug: str, dates: str) -> list[dict[str, Any]]:
        """GET /{league}/scoreboard?dates=YYYYMMDD[-YYYYMMDD] → events list."""
        url = f"{BASE_URL}/{league_slug}/scoreboard"
        params = {"dates": dates, "limit": "200"}
        last_exc: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.BACKOFF_SECONDS[attempt])
                    continue
                raise EspnError(f"Network error after {self.MAX_RETRIES} attempts: {exc}") from exc

            if resp.status_code >= 400:
                raise EspnError(f"HTTP {resp.status_code} for {url}: {resp.text[:200]}")

            payload = resp.json()
            return list(payload.get("events", []))

        raise EspnError(f"Exhausted retries for {url}; last error: {last_exc}")

    async def get_summary(self, league_slug: str, event_id: str) -> dict[str, Any]:
        """GET /{league}/summary?event={id} → full event-summary payload.

        Used to read a knockout's authoritative per-period `linescores`
        (regulation / extra time / shootout) once it has gone past 90'.
        """
        url = f"{BASE_URL}/{league_slug}/summary"
        params = {"event": event_id}
        last_exc: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.BACKOFF_SECONDS[attempt])
                    continue
                raise EspnError(f"Network error after {self.MAX_RETRIES} attempts: {exc}") from exc

            if resp.status_code >= 400:
                raise EspnError(f"HTTP {resp.status_code} for {url}: {resp.text[:200]}")

            return dict(resp.json())

        raise EspnError(f"Exhausted retries for {url}; last error: {last_exc}")

"""External score fetching service.

Two providers, ESPN-first:
  - ESPN (unofficial public JSON) paints LIVE in-play scores — near
    real-time, no auth — and emits finished matches as non-authoritative
    finals (good enough to finish a group match instantly; knockout
    finals wait for the FT/ET/pens split).
  - Football-Data.org is the authoritative finisher for knockout matches
    (proper FT/ET/pens split via the per-fixture resolution pass) and the
    bulk fallback if ESPN errors on a tick. Its free tier omits in-play
    scores (fullTime stays null until their delayed feed finishes the
    match), so scores are kept None when absent — never coerced to 0.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta

from app.models._datetime import utc_now
from app.models.fixture import MatchStatus
from app.services.external.espn import (
    EspnClient,
    LEAGUE_SLUGS,
    canonical_team_name,
    competition_past_regulation,
    map_event_status,
    parse_minute,
    parse_summary_split,
)
from app.services.external.football_data import FootballDataClient, map_status


logger = logging.getLogger(__name__)


@dataclass
class ExternalScore:
    """Score data from external API.

    home_score/away_score are None when the provider reported a match
    without score data (Football-Data's free tier does this for in-play
    matches). Consumers must never coerce None to 0 — that fabricates a
    0-0 result.
    """

    external_id: str
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    status: MatchStatus
    minute: int | None = None
    # Match period (soccer): 1/2 = halves (regulation), 3/4 = extra time,
    # 5 = shootout. >2 means the match went PAST regulation — used to freeze
    # the 90-minute score for knockout grading (ESPN folds ET into the running
    # total). None when the provider doesn't expose it (Football-Data).
    period: int | None = None
    home_score_et: int | None = None
    away_score_et: int | None = None
    home_penalties: int | None = None
    away_penalties: int | None = None
    # True when a FINISHED status carries the full result our scoring needs
    # (Football-Data: FT/ET/pens split; or an ESPN knockout enriched from the
    # summary endpoint's per-period linescores). A bare ESPN scoreboard event
    # folds ET goals into one running total, so it reports finals as
    # non-authoritative — accepted as final for group-stage fixtures only.
    final_authoritative: bool = True
    # ESPN scoreboard event id, used only to fetch that event's summary for the
    # knockout per-period split. Not a fixture match key — matching still goes
    # through external_id / team names. None for non-ESPN providers.
    espn_event_id: str | None = None


class ScoreProviderBase(ABC):
    """Base class for score providers (kept abstract for testability)."""

    @abstractmethod
    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        ...

    @abstractmethod
    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        ...

    async def fetch_final_check(
        self, ext: "ExternalScore"
    ) -> tuple[int, int, int | None, int | None] | None:
        """An independent, authoritative `(final_home, final_away, pen_home,
        pen_away)` for a just-finished match, used to cross-check the value we
        are about to store. `final_*` is the after-ET total (= the regulation
        total for matches that didn't go to ET). None when no independent check
        is available — the default for providers that can't offer one."""
        return None


class FootballDataScoreProvider(ScoreProviderBase):
    """Live-score provider using football-data.org via the shared client."""

    LIVE_STATUS_FILTER = "LIVE,IN_PLAY,PAUSED"

    def __init__(self, client: FootballDataClient | None = None) -> None:
        self._client = client or FootballDataClient()

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        """Fetch live scores for a competition (e.g. competition_id='WC')."""
        matches = await self._client.get_matches(competition_id, status=self.LIVE_STATUS_FILTER)
        return [self._to_external_score(m) for m in matches]

    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        match = await self._client.get_match(fixture_id)
        if match is None:
            return None
        return self._to_external_score(match)

    @staticmethod
    def _to_external_score(match: dict) -> ExternalScore:
        score = match.get("score") or {}
        full_time = score.get("fullTime") or {}
        extra_time = score.get("extratime") or score.get("extraTime") or {}
        penalty = score.get("penalty") or score.get("penalties") or {}
        home_team = match.get("homeTeam") or {}
        away_team = match.get("awayTeam") or {}

        return ExternalScore(
            external_id=str(match.get("id", "")),
            home_team=home_team.get("name") or "",
            away_team=away_team.get("name") or "",
            # None stays None: the free tier reports null fullTime for
            # in-play matches, and `or 0` here once fabricated a 0-0 final.
            home_score=full_time.get("home"),
            away_score=full_time.get("away"),
            status=map_status(match.get("status", "")),
            minute=match.get("minute"),
            home_score_et=extra_time.get("home"),
            away_score_et=extra_time.get("away"),
            home_penalties=penalty.get("home"),
            away_penalties=penalty.get("away"),
        )


class EspnScoreProvider(ScoreProviderBase):
    """Live in-play scores from ESPN's public scoreboard JSON.

    Emits pre/in-play matches plus completed ones as NON-authoritative
    finals (`final_authoritative=False`): the apply layer accepts those as
    final for group-stage fixtures (no ET/pens to split) and treats them
    as live paints for knockout fixtures, where the Football-Data
    resolution pass still lands the authoritative FT/ET/pens result.

    ExternalScore.external_id is left blank — ESPN event ids don't match
    the Football-Data ids stored on fixtures, so matching goes through the
    (home_team, away_team) name fallback with ESPN→canonical aliases.
    """

    def __init__(self, client: EspnClient | None = None) -> None:
        self._client = client or EspnClient()

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        slug = LEAGUE_SLUGS.get(competition_id, "fifa.world")
        # ESPN buckets events by US-Eastern calendar day; a ±1-day UTC window
        # always covers anything currently in play (incl. 02:00Z kickoffs).
        now = utc_now()
        dates = (
            f"{(now - timedelta(days=1)).strftime('%Y%m%d')}"
            f"-{(now + timedelta(days=1)).strftime('%Y%m%d')}"
        )
        events = await self._client.get_scoreboard(slug, dates)
        scores: list[ExternalScore] = []
        to_enrich: list[ExternalScore] = []
        for event in events:
            ext = self._to_external_score(event)
            if ext is None:
                continue
            scores.append(ext)
            try:
                comp = event["competitions"][0]
            except (KeyError, IndexError, TypeError):
                comp = {}
            if ext.espn_event_id and competition_past_regulation(comp):
                to_enrich.append(ext)

        if to_enrich:
            await self._enrich_knockout_splits(slug, to_enrich)
        return scores

    async def _enrich_knockout_splits(
        self, slug: str, scores: list[ExternalScore]
    ) -> None:
        """Overlay the authoritative per-period split onto each past-regulation
        knockout score, in place, from its summary endpoint.

        On any failure (HTTP error, or a summary that is missing / inconsistent
        / a still-undecided shootout) the base score is left untouched, so
        score_sync's freeze remains the fallback. Fetches run concurrently —
        there are only ever a handful of knockout matches past 90' at once.
        """

        async def overlay(ext: ExternalScore) -> None:
            # Enrichment is best-effort: ANY failure (HTTP, malformed JSON, a
            # parser surprise) must skip this one match, never break the tick —
            # score_sync's freeze remains the fallback.
            try:
                summary = await self._client.get_summary(slug, ext.espn_event_id)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "espn summary fetch failed for event %s (%s vs %s): %s",
                    ext.espn_event_id, ext.home_team, ext.away_team, exc,
                )
                return
            split = parse_summary_split(summary)
            if split is None:
                logger.warning(
                    "espn summary split unavailable/inconsistent for %s vs %s "
                    "(event %s) — leaving running total for score_sync to handle",
                    ext.home_team, ext.away_team, ext.espn_event_id,
                )
                return
            ext.home_score = split.home_reg
            ext.away_score = split.away_reg
            ext.home_score_et = split.home_et
            ext.away_score_et = split.away_et
            ext.home_penalties = split.home_pen
            ext.away_penalties = split.away_pen
            ext.final_authoritative = True

        await asyncio.gather(*(overlay(s) for s in scores))

    async def fetch_final_check(
        self, ext: ExternalScore
    ) -> tuple[int, int, int | None, int | None] | None:
        """Read the authoritative final from this event's summary linescores.

        Used by score_sync to validate a match it is finalizing from the
        scoreboard running total (groups, regulation-decided knockouts) — the
        catch-all so EVERY settled match is checked against ESPN's per-period
        truth, not just the ET/penalty knockouts the live path already overlays.
        """
        if not ext.espn_event_id:
            return None
        # WC2026 is the only competition; its ESPN slug is the LEAGUE_SLUGS
        # default. (fetch_final_check isn't given the competition id.)
        slug = LEAGUE_SLUGS.get("WC", "fifa.world")
        try:
            summary = await self._client.get_summary(slug, ext.espn_event_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "espn final-check summary fetch failed for event %s: %s",
                ext.espn_event_id, exc,
            )
            return None
        split = parse_summary_split(summary)
        if split is None:
            return None
        final_home = split.home_et if split.home_et is not None else split.home_reg
        final_away = split.away_et if split.away_et is not None else split.away_reg
        return (final_home, final_away, split.home_pen, split.away_pen)

    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        # Per-fixture lookups are keyed by Football-Data external ids, which
        # ESPN can't resolve — the fallback provider routes these to FD.
        return None

    @staticmethod
    def _to_external_score(event: dict) -> ExternalScore | None:
        try:
            comp = event["competitions"][0]
            status = map_event_status(comp.get("status", {}).get("type", {}))
            if status is None:
                return None  # abandoned/postponed — nothing to paint
            sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            home, away = sides.get("home"), sides.get("away")
            if not home or not away:
                return None
            shootout_home = home.get("shootoutScore")
            shootout_away = away.get("shootoutScore")
            raw_period = comp.get("status", {}).get("period")
            period = int(raw_period) if isinstance(raw_period, (int, float)) else None
            return ExternalScore(
                external_id="",
                home_team=canonical_team_name(home.get("team", {}).get("displayName", "")),
                away_team=canonical_team_name(away.get("team", {}).get("displayName", "")),
                home_score=int(home.get("score") or 0),
                away_score=int(away.get("score") or 0),
                status=status,
                minute=parse_minute(comp.get("status", {}).get("displayClock")),
                period=period,
                home_penalties=int(shootout_home) if shootout_home is not None else None,
                away_penalties=int(shootout_away) if shootout_away is not None else None,
                # ESPN's scoreboard score is one running total (ET goals folded
                # in) — fine to finish a group match, not a knockout one. A
                # knockout past 90' is upgraded to authoritative once its
                # summary linescores are overlaid (see _enrich_knockout_splits).
                final_authoritative=False,
                espn_event_id=str(event.get("id")) if event.get("id") is not None else None,
            )
        except (KeyError, IndexError, TypeError, ValueError):
            return None  # one malformed event shouldn't poison the tick


class FallbackScoreProvider(ScoreProviderBase):
    """ESPN-first chain: live scores try each provider in order, falling
    through on exceptions; per-fixture resolution always goes to
    Football-Data (it owns the external ids and the FT/ET/pens split)."""

    def __init__(
        self,
        live_providers: list[ScoreProviderBase],
        resolver: ScoreProviderBase,
    ) -> None:
        self._live_providers = live_providers
        self._resolver = resolver

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        last_exc: Exception | None = None
        for provider in self._live_providers:
            try:
                return await provider.fetch_live_scores(competition_id)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "score provider %s failed, trying next: %s",
                    type(provider).__name__,
                    exc,
                )
        raise last_exc if last_exc else RuntimeError("no live score providers configured")

    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        return await self._resolver.fetch_fixture_score(fixture_id)

    async def fetch_final_check(
        self, ext: ExternalScore
    ) -> tuple[int, int, int | None, int | None] | None:
        """Delegate to the first live provider that offers an independent check
        (ESPN, via its summary). Never raises — a failed check just means no
        cross-check this settlement."""
        for provider in self._live_providers:
            try:
                check = await provider.fetch_final_check(ext)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "final-check provider %s failed: %s", type(provider).__name__, exc
                )
                continue
            if check is not None:
                return check
        return None


def get_score_provider() -> ScoreProviderBase:
    """ESPN paints live scores and finishes group-stage matches
    (Football-Data bulk as same-tick fallback); Football-Data resolves
    knockout finals (FT/ET/pens split). No configuration on purpose —
    nothing to wire into prod env, and the fallback engages by itself
    per tick.
    """
    football_data = FootballDataScoreProvider()
    return FallbackScoreProvider(
        live_providers=[EspnScoreProvider(), football_data],
        resolver=football_data,
    )

"""Score-sync service: pull live scores from external API and write to DB.

Extracted from the admin endpoint so the same code path can be invoked by:
- The admin sync endpoint (manual trigger)
- The background scheduler (automatic polling during match windows)

Returns counts + errors as a dataclass (no FastAPI types here).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models._datetime import aware_utc, utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource
from app.services.external_scores import ExternalScore, get_score_provider

logger = logging.getLogger(__name__)
from app.services.leaderboard import invalidate_cache


@dataclass
class ScoreSyncResult:
    synced: int = 0       # newly created Score rows
    updated: int = 0      # existing Score rows updated
    errors: list[str] = field(default_factory=list)
    skipped_reason: str | None = None  # set if sync was a no-op (e.g. no live matches)


# Window during which we consider a match worth polling for.
# Pre-kickoff buffer catches kick-off transitions; post-finish buffer
# catches final whistle and any AET / penalty resolution.
_PRE_KICKOFF_BUFFER = timedelta(minutes=10)
_POST_FINISH_BUFFER = timedelta(minutes=10)
_LIVE_MATCH_WINDOW = timedelta(hours=4)  # generous upper bound (group + ET + pens)

# Cap on per-fixture resolution fetches in a single sync. Each costs one
# API call on top of the bulk live call; Free tier allows 10/min, so 8
# keeps a worst-case tick (1 bulk + 8 singles) inside the budget.
_MAX_RESOLVE_FETCHES = 8


async def has_active_or_imminent_match(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> bool:
    """Return True if there's any reason to poll the API right now.

    Cheap DB query; no external calls. The scheduler uses this to decide
    whether to skip a tick (saves API quota during off-windows).
    """
    now = now or utc_now()

    # 1. Anything currently live? Always poll.
    live_q = await session.execute(
        select(Fixture.id)
        .where(Fixture.status.in_([MatchStatus.LIVE, MatchStatus.HALFTIME]))
        .limit(1)
    )
    if live_q.scalar_one_or_none() is not None:
        return True

    # 2. Anything scheduled to kick off within the pre-kickoff buffer? Poll.
    upcoming_q = await session.execute(
        select(Fixture.id)
        .where(
            Fixture.status == MatchStatus.SCHEDULED,
            Fixture.kickoff <= now + _PRE_KICKOFF_BUFFER,
            Fixture.kickoff >= now - _LIVE_MATCH_WINDOW,
        )
        .limit(1)
    )
    if upcoming_q.scalar_one_or_none() is not None:
        return True

    # 3. Anything scheduled but in the live-match window (in case status didn't
    # update from SCHEDULED → LIVE due to a polling miss)? Poll.
    return False


async def sync_scores_once(session: AsyncSession) -> ScoreSyncResult:
    """Fetch live scores from the configured provider and update DB.

    Returns counts + any errors encountered. Idempotent: re-running on
    unchanged data results in zero new rows.
    """
    result = ScoreSyncResult()

    comp_q = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = comp_q.scalar_one_or_none()

    if not competition or not competition.external_id:
        result.errors.append("No active competition with external_id configured")
        return result

    provider = get_score_provider()

    try:
        external_scores = await provider.fetch_live_scores(competition.external_id)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Provider error: {exc}")
        return result

    # Fixtures the live response actually touched this tick (by row id, NOT
    # external id — the ESPN provider matches by team name and carries no
    # Football-Data id, so id-string bookkeeping would mark everything
    # unresolved and let a laggier source overwrite fresh live scores).
    seen_fixture_ids: set = set()
    for ext in external_scores:
        try:
            touched = await _apply_external_score(session, competition.id, ext, result)
            if touched is not None:
                seen_fixture_ids.add(touched)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                f"Error applying {ext.home_team} vs {ext.away_team}: {exc}"
            )

    # Resolution pass. The live feed only covers pre/in-play matches (ESPN
    # drops finished ones by design; Football-Data's bulk call filters on
    # LIVE/IN_PLAY/PAUSED) — so the moment a match ends it vanishes from
    # the response, and without this pass its fixture would sit at LIVE
    # with the last in-play score forever (blocking scoring + pushes).
    # Any fixture we believe is in-play (or that kicked off recently but
    # never transitioned, e.g. after backend downtime) that the live
    # response did not touch gets fetched from Football-Data by external
    # id — landing the authoritative final with the FT/ET/pens split.
    unresolved = await _find_unresolved_fixtures(session, competition.id, seen_fixture_ids)
    for fixture in unresolved[:_MAX_RESOLVE_FETCHES]:
        try:
            ext = await provider.fetch_fixture_score(fixture.external_id)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                f"Resolve error for {fixture.home_team} vs {fixture.away_team}: {exc}"
            )
            continue
        if ext is None:
            continue
        try:
            await _apply_external_score(session, competition.id, ext, result)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                f"Error applying {ext.home_team} vs {ext.away_team}: {exc}"
            )

    if not external_scores and not unresolved:
        result.skipped_reason = "no live matches returned by provider"
        return result

    await session.commit()

    if result.synced > 0 or result.updated > 0:
        invalidate_cache()

    return result


async def _find_unresolved_fixtures(
    session: AsyncSession,
    competition_id,
    seen_fixture_ids: set,
    *,
    now: datetime | None = None,
) -> list[Fixture]:
    """Fixtures that should be in the live response but weren't.

    Two shapes: (a) status LIVE/HALFTIME — almost certainly just finished;
    (b) status SCHEDULED with a kickoff in the recent past — a transition
    we missed entirely (e.g. the backend was down through the match).
    """
    now = now or utc_now()
    q = await session.execute(
        select(Fixture).where(
            Fixture.competition_id == competition_id,
            Fixture.external_id.is_not(None),  # type: ignore[union-attr]
            (
                Fixture.status.in_([MatchStatus.LIVE, MatchStatus.HALFTIME])
                | (
                    (Fixture.status == MatchStatus.SCHEDULED)
                    & (Fixture.kickoff <= now)
                    & (Fixture.kickoff >= now - _LIVE_MATCH_WINDOW)
                )
            ),
        )
    )
    return [f for f in q.scalars().all() if f.id not in seen_fixture_ids]


# Statuses for which the provider's score payload is meaningful. For a
# match that hasn't started (or won't be played) the score is meaningless
# even if present, so the Score row is only touched in these states (and
# only when the payload actually carries scores — see _apply_external_score).
_SCORE_BEARING_STATUSES = frozenset(
    {MatchStatus.LIVE, MatchStatus.HALFTIME, MatchStatus.FINISHED}
)


def _score_fields_for(
    fixture: Fixture, ext: ExternalScore, existing: Score | None
) -> tuple[int, int, int | None, int | None, int | None, int | None]:
    """Compute (home, away, home_et, away_et, home_pen, away_pen) to persist,
    applying the 90-minute freeze for knockout extra time.

    Knockout SCORE grading is on the 90-minute result (`Score.regulation_outcome`
    = home_score vs away_score). ESPN, our live source, reports ONE running total
    with extra-time goals folded into home_score/away_score and exposes no 90'
    split — only the period (>2 once the match passes regulation). So once a
    knockout fixture is past regulation we must NOT overwrite home_score/
    away_score (they hold the 90' result captured on the last regulation tick);
    the running total becomes the after-ET score in *_et instead, and the
    shootout (if any) sits in penalties. `outcome` then still resolves
    advancement via ET → penalties, while regulation grading stays true to 90'.

    Providers that already split ET themselves carry an explicit *_et — the ESPN
    summary enrichment (per-period linescores) and Football-Data both do — so they
    skip the freeze entirely and pass their authoritative 90'/ET values straight
    through. The freeze below is only the fallback for a bare ESPN running total.
    """
    provider_split = ext.home_score_et is not None and ext.away_score_et is not None
    past_regulation = (
        fixture.stage != "group"
        and not provider_split
        and ext.period is not None
        and ext.period > 2
    )
    if not past_regulation:
        return (
            ext.home_score,
            ext.away_score,
            ext.home_score_et,
            ext.away_score_et,
            ext.home_penalties,
            ext.away_penalties,
        )

    # Past regulation with a bare running-total provider (summary enrichment
    # unavailable). Freeze the 90' score at whatever was captured during
    # regulation; the running total is the after-ET score.
    if existing is not None:
        reg_home, reg_away = existing.home_score, existing.away_score
    else:
        # Never observed this match during regulation (a polling gap) — we have
        # no true 90' score. Best effort: keep the running total, and flag it so
        # the admin can correct via the manual Score editor.
        reg_home, reg_away = ext.home_score, ext.away_score
        logger.warning(
            "score_sync: knockout fixture %s first seen past regulation "
            "(period=%s) — no captured 90' score; using running total %s-%s, "
            "admin should verify",
            fixture.id, ext.period, ext.home_score, ext.away_score,
        )

    # The running total IS the after-ET score for a bare provider.
    home_et = ext.home_score_et if ext.home_score_et is not None else ext.home_score
    away_et = ext.away_score_et if ext.away_score_et is not None else ext.away_score

    # Self-heal corrupted live captures. Goals only accumulate, so a side's 90'
    # score can never exceed its after-ET total. A frozen reg above the ET total
    # means the live capture was polluted (e.g. ESPN folds shootout goals into
    # the running `score` while period still reads <=2, so the freeze never
    # engaged and an inflated total was stored as the "90' score"). Clamp it
    # back to the ET total — which, once the match completes, is the clean
    # after-ET running total — so the result self-corrects without a manual fix.
    if home_et is not None and reg_home > home_et:
        logger.warning(
            "score_sync: knockout fixture %s frozen 90' home %s exceeds after-ET "
            "total %s — corrupted live capture, healing 90' to ET total",
            fixture.id, reg_home, home_et,
        )
        reg_home = home_et
    if away_et is not None and reg_away > away_et:
        logger.warning(
            "score_sync: knockout fixture %s frozen 90' away %s exceeds after-ET "
            "total %s — corrupted live capture, healing 90' to ET total",
            fixture.id, reg_away, away_et,
        )
        reg_away = away_et

    return (reg_home, reg_away, home_et, away_et, ext.home_penalties, ext.away_penalties)


async def _apply_external_score(
    session: AsyncSession,
    competition_id,
    ext: ExternalScore,
    result: ScoreSyncResult,
):
    """Match an ExternalScore to a Fixture by external_id (or team-name fallback)
    and create/update the corresponding Score row.

    Returns the touched fixture's id (or None if no fixture matched, or if
    the fixture still needs the resolution pass this tick) so the caller
    can exclude resolved fixtures from that pass."""
    fixture = await _find_fixture(session, competition_id, ext)
    if fixture is None:
        return None

    has_scores = ext.home_score is not None and ext.away_score is not None

    status = ext.status
    needs_resolution = False
    if status == MatchStatus.FINISHED:
        if not has_scores:
            # The provider says finished but sent no score (Football-Data's
            # delayed free feed does this transiently). Marking FINISHED now
            # would freeze the fixture on whatever score is stored and stop
            # the resolution pass — leave everything untouched and retry.
            return None
        if (
            not ext.final_authoritative
            and fixture.stage != "group"
            and utc_now() < aware_utc(fixture.kickoff) + _LIVE_MATCH_WINDOW
        ):
            # ESPN final on a knockout fixture: the score is one running
            # total without the FT/ET/pens split scoring prefers. Paint it
            # as a live update and keep the fixture eligible for
            # Football-Data resolution (returning None keeps it in this
            # tick's pass). But only within the live-match window — the
            # free FD tier has been observed returning FINISHED with null
            # scores indefinitely (opening match, 2026-06-11), so past the
            # window ESPN's final (total + shootout) is accepted rather
            # than holding the fixture LIVE forever.
            status = MatchStatus.LIVE
            needs_resolution = True

    fixture.status = status
    fixture.minute = ext.minute
    fixture.updated_at = utc_now()

    if status not in _SCORE_BEARING_STATUSES:
        return fixture.id

    if not has_scores:
        # Score-bearing status with no score payload (Football-Data's free
        # tier omits in-play scores). Writing the nulls coerced to 0 would
        # fabricate a 0-0 — keep the stored score (e.g. ESPN's live paint).
        return fixture.id

    score_q = await session.execute(select(Score).where(Score.fixture_id == fixture.id))
    score = score_q.scalar_one_or_none()

    home, away, home_et, away_et, home_pen, away_pen = _score_fields_for(
        fixture, ext, score
    )

    if score is None:
        session.add(
            Score(
                fixture_id=fixture.id,
                home_score=home,
                away_score=away,
                home_score_et=home_et,
                away_score_et=away_et,
                home_penalties=home_pen,
                away_penalties=away_pen,
                source=ScoreSource.API,
            )
        )
        result.synced += 1
        return None if needs_resolution else fixture.id

    score.home_score = home
    score.away_score = away
    score.home_score_et = home_et
    score.away_score_et = away_et
    score.home_penalties = home_pen
    score.away_penalties = away_pen
    score.source = ScoreSource.API
    score.updated_at = utc_now()
    result.updated += 1
    return None if needs_resolution else fixture.id


async def _find_fixture(
    session: AsyncSession, competition_id, ext: ExternalScore
) -> Fixture | None:
    """Match by external_id first; fall back to (home_team, away_team) within competition."""
    if ext.external_id:
        q = await session.execute(
            select(Fixture).where(Fixture.external_id == ext.external_id)
        )
        f = q.scalar_one_or_none()
        if f is not None:
            return f

    if ext.home_team and ext.away_team:
        q = await session.execute(
            select(Fixture).where(
                Fixture.home_team == ext.home_team,
                Fixture.away_team == ext.away_team,
                Fixture.competition_id == competition_id,
            )
        )
        return q.scalar_one_or_none()

    return None

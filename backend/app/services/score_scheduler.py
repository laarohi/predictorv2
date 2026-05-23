"""Background scheduler that polls live scores during match windows.

Runs as an asyncio task started during FastAPI lifespan. Each tick:
  1. Cheap DB query to decide if any match is live or imminent.
  2. If yes, call sync_scores_once (one external API call).
  3. Sleep for POLL_INTERVAL_SECONDS.

Outside match windows the scheduler does no API work — saves quota and
keeps us comfortably under Football-Data Free tier's 10 calls/min limit.
A typical match-day burns ~30-90 calls (one per minute over 1.5h);
budget is 14,400/day so we're well below the ceiling.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models._datetime import utc_now
from app.services.locking import get_active_competition
from app.services.receipts import send_phase1_receipts
from app.services.score_sync import has_active_or_imminent_match, sync_scores_once
from app.services.snapshots import take_daily_snapshots


logger = logging.getLogger(__name__)


# Tunable: 60 s lines up with the frontend's leaderboard poll cadence,
# so users see fresh scores within one frontend refresh.
POLL_INTERVAL_SECONDS = 60.0


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    settings = get_settings()
    db_url = str(settings.database_url).replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(db_url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _run_one_tick(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """One iteration of the loop. Wraps each tick in its own session so a
    failure on one tick can't poison subsequent ticks.

    Each tick does three things:
      (a) Take today's leaderboard snapshot if not already taken (idempotent
          per-user-per-day, cheap no-op after the first call of the day).
      (b) Send Phase 1 receipt emails to any users who haven't received
          one yet, but only if the competition's phase1_deadline has
          passed. Idempotent via the email_sends table — duplicate
          ticks won't re-send.
      (c) If a match is live or imminent, sync scores from Football-Data.

    Each side-task has its own try/except so a failure in one can't break
    the others.
    """
    async with session_factory() as session:
        try:
            await take_daily_snapshots(session)
        except Exception:  # noqa: BLE001
            logger.exception("score_scheduler: snapshot tick failed")

        try:
            await _maybe_send_phase1_receipts(session)
        except Exception:  # noqa: BLE001
            logger.exception("score_scheduler: phase1 receipt tick failed")

        if not await has_active_or_imminent_match(session):
            return
        result = await sync_scores_once(session)
        if result.errors:
            for err in result.errors:
                logger.warning("score_scheduler: %s", err)
        if result.synced or result.updated:
            logger.info(
                "score_scheduler tick: synced=%d updated=%d",
                result.synced,
                result.updated,
            )


async def _maybe_send_phase1_receipts(session: AsyncSession) -> None:
    """Gate the receipt send on the deadline having passed.

    Three conditions all need to be true:
      - There is an active competition.
      - It has a phase1_deadline set.
      - That deadline is in the past.

    If all three hold, call send_phase1_receipts. The batch function
    is itself idempotent (skips users already in email_sends), so
    calling it on every tick after the deadline is harmless — it'll
    no-op once everyone's been sent.
    """
    competition = await get_active_competition(session)
    if not competition or not competition.phase1_deadline:
        return
    if utc_now() < competition.phase1_deadline:
        return

    result = await send_phase1_receipts(session, competition)
    # Only log when we actually did something — chatty logs would
    # spam every minute forever once the deadline passes.
    if result.sent or result.failed:
        logger.info(
            "score_scheduler: phase1 receipts — sent=%d failed=%d "
            "skipped_already_sent=%d skipped_no_predictions=%d "
            "skipped_no_api_key=%d skipped_not_in_allowlist=%d",
            result.sent, result.failed,
            result.skipped_already_sent, result.skipped_no_predictions,
            result.skipped_no_api_key, result.skipped_not_in_allowlist,
        )


async def run_scheduler_loop(
    *,
    interval_seconds: float = POLL_INTERVAL_SECONDS,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Long-running task: poll forever (until cancelled or stop_event set)."""
    session_factory = _make_session_factory()
    stop_event = stop_event or asyncio.Event()

    logger.info("score_scheduler started (interval=%.1fs)", interval_seconds)
    try:
        while not stop_event.is_set():
            try:
                await _run_one_tick(session_factory)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                # Log but never let one bad tick kill the loop.
                logger.exception("score_scheduler: tick failed")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                # If wait returned, stop_event was set — exit loop.
                return
            except asyncio.TimeoutError:
                # Timed out waiting → another tick is due.
                continue
    except asyncio.CancelledError:
        logger.info("score_scheduler cancelled")
        raise
    finally:
        logger.info("score_scheduler stopped")


@asynccontextmanager
async def scheduler_lifespan():
    """Async context manager that starts the scheduler on enter and
    stops it cleanly on exit. Used by FastAPI's lifespan handler.
    """
    stop_event = asyncio.Event()
    task = asyncio.create_task(run_scheduler_loop(stop_event=stop_event))
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

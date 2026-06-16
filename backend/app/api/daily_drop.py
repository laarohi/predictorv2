"""Daily Drop endpoints — the once-a-day broadcast banter card.

- ``GET  /daily-drop/latest`` — the most recent Drop (stats + maybe roast) for
  the once-per-day modal. Auth required (friends-only); returns ``null`` when no
  Drop has been built yet.
- ``POST /daily-drop/build`` — admin: (re)compute today's Drop immediately. A
  dev/ops trigger; the scheduler will call the same builder on a morning cadence
  later.
"""

from sqlmodel import select

from fastapi import APIRouter

from app.dependencies import AdminUser, CurrentUser, DbSession
from app.models.daily_drop import DailyDrop
from app.schemas.daily_drop import DailyDropResponse, DropPayload, PersonalStats
from app.services.daily_drop import (
    build_daily_drop,
    compute_personal_stats,
    placeholder_roast,
)

router = APIRouter()


def _to_response(
    drop: DailyDrop, personal: PersonalStats | None = None
) -> DailyDropResponse:
    payload = DropPayload.model_validate(drop.payload)
    # Until Phase C wires the real (subscription-generated) roast, synthesise a
    # stand-in at response time so the card is fully visualisable. Not persisted.
    is_placeholder = drop.roast is None
    roast = placeholder_roast(payload) if is_placeholder else drop.roast
    return DailyDropResponse(
        drop_date=drop.drop_date,
        payload=payload,
        roast=roast,
        roast_is_placeholder=is_placeholder,
        roast_generated_at=drop.roast_generated_at,
        created_at=drop.created_at,
        personal=personal,
    )


@router.get("/latest", response_model=DailyDropResponse | None)
async def get_latest_drop(
    session: DbSession, user: CurrentUser
) -> DailyDropResponse | None:
    """The most recent Drop, or ``null`` if none has been built yet."""
    drop = (
        await session.execute(
            select(DailyDrop).order_by(DailyDrop.drop_date.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if not drop:
        return None
    personal = await compute_personal_stats(session, user.id)
    return _to_response(drop, personal)


@router.post("/build", response_model=DailyDropResponse)
async def build_drop_now(session: DbSession, _admin: AdminUser) -> DailyDropResponse:
    """Admin: recompute today's Drop right now (force). Used in dev/ops; the
    scheduler will own the daily cadence."""
    drop = await build_daily_drop(session, force=True)
    return _to_response(drop)

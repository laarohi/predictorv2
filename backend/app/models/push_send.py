"""Idempotency record for sent push notifications.

Mirrors :class:`EmailSend`. One row per (user, kind, ref_id) *successful*
push, so the scheduler can evaluate a trigger every tick without ever
re-notifying:

    kind            ref_id          fires
    lock_reminder   fixture_id      once per user per imminent match
    result          fixture_id      once per user per finished match
    phase2_opened   competition_id  once per user when knockouts open

Written only after the push service accepts the send (transient failures
deliberately do NOT write a row, so the next tick retries — same contract
as EmailSend).

``ref_id`` is a plain UUID, not a foreign key: it points at a fixture OR a
competition depending on ``kind``, so it can't carry one FK.
"""

import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint  # noqa: F401 (consumed via __table_args__)
from sqlmodel import Field, SQLModel

from app.models._datetime import utc_datetime_column, utc_now


class PushSend(SQLModel, table=True):
    """One row per (user, kind, ref_id) successful push send."""

    __tablename__ = "push_sends"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "ref_id", name="uq_push_send_user_kind_ref"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    # "lock_reminder" | "result" | "phase2_opened"
    kind: str = Field(index=True, max_length=32)
    # fixture_id for lock_reminder/result, competition_id for phase2_opened.
    ref_id: uuid.UUID = Field(index=True)

    sent_at: datetime = Field(
        default_factory=utc_now,
        sa_column=utc_datetime_column(index=True),
    )

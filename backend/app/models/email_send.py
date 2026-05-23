"""Idempotency record for sent deadline-receipt emails.

Each row represents a *successful* receipt send. The unique
constraint on (user_id, competition_id, deadline_kind) prevents
double-sends — the batch sender SELECTs this table at the start of
each user's turn and skips users who already have a row.

Append-only:
- Only written after a Resend send returns 200.
- Transient failures (5xx, network) deliberately do NOT write a row,
  so the next scheduler tick retries them.
- Permanent failures (4xx) currently log loudly without writing —
  admin investigates. A future revision could write a row with
  `error` populated to stop retrying on persistent failures.

The `resend_message_id` is preserved so an admin can correlate any
delivery problem back to Resend's dashboard log.
"""

import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint  # noqa: F401 (consumed via __table_args__)
from sqlmodel import Field, SQLModel

from app.models._datetime import utc_datetime_column, utc_now


class EmailSend(SQLModel, table=True):
    """One row per (user, competition, deadline-kind) successful send."""

    __tablename__ = "email_sends"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "competition_id", "deadline_kind",
            name="uq_email_send_user_competition_deadline",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    competition_id: uuid.UUID = Field(foreign_key="competitions.id", index=True)

    # Which deadline this receipt covers. Today: "phase1"; later we'll
    # add "phase2_bracket" and possibly "final_standings".
    deadline_kind: str = Field(index=True, max_length=32)

    # Resend's message id — useful for cross-referencing against the
    # Resend dashboard if a delivery query comes in.
    resend_message_id: str | None = Field(default=None, max_length=128)

    sent_at: datetime = Field(
        default_factory=utc_now,
        sa_column=utc_datetime_column(index=True),
    )

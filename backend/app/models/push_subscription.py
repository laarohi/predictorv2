"""A browser/device Web Push subscription.

One row per push endpoint (a device's installed PWA). Created when the user
taps "Enable notifications" inside the home-screen app: the browser hands us
its push-service endpoint plus the two encryption keys (p256dh, auth) that
the sender (services/push.py) needs to encrypt payloads (RFC 8291).

iOS realities that shaped this model:
- Web Push only works inside an installed (home-screen) PWA over HTTPS.
- On logout we set ``active = False`` rather than browser-unsubscribing —
  iOS won't let us silently re-subscribe later, so we keep the channel and
  just stop sending until the user logs back in (then reactivate).
- A 410 Gone / 404 from the push service means the subscription is dead;
  the sender DELETEs the row.

``endpoint`` is globally unique — it identifies one device's push channel.
On re-subscribe we upsert by endpoint (e.g. a shared device re-pointed at
whoever is currently logged in).
"""

import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint  # noqa: F401 (consumed via __table_args__)
from sqlmodel import Field, SQLModel

from app.models._datetime import utc_datetime_column, utc_now


class PushSubscription(SQLModel, table=True):
    """One row per Web Push endpoint (device)."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_push_subscription_endpoint"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)

    # The push-service URL (web.push.apple.com / fcm.googleapis.com / ...).
    endpoint: str
    # Keys from PushSubscription.toJSON().keys — base64url strings used to
    # encrypt the payload. p256dh is the client public key, auth the secret.
    p256dh: str
    auth: str

    # Logout flips this to False instead of unsubscribing (see module docstring).
    active: bool = Field(default=True, index=True)
    # Best-effort device label, for telling a user's devices apart in admin.
    user_agent: str | None = Field(default=None, max_length=512)

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

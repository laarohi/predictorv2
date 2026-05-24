"""One-time magic-link tokens for passwordless email login.

Each row represents a token *issued* to a user — created when they
request a magic link, verified-and-marked-used when they click the
link in the email.

Storage rules:
- `token_hash` is sha256(raw_token), hex-encoded. The raw token only
  ever exists in the user's inbox; a leaked DB yields hashes, which
  are useless without the source.
- `used_at` is None until verify consumes the token; once set, the
  token cannot be reused.
- `expires_at` is the soft TTL (15 min from issuance by default).
  Verify rejects expired rows even if unused.
- When a user requests a NEW link, prior unused tokens for the same
  user are marked used (revoked) — limits the "valid token" window
  to the most recent request.

The table is queried two ways:
  1. by `token_hash` at verify-time (must be indexed for O(1) lookup).
  2. by `user_id` for the revoke-prior pass and rate-limit counting.
"""

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models._datetime import utc_datetime_column, utc_now


class MagicLinkToken(SQLModel, table=True):
    """One row per magic-link issuance."""

    __tablename__ = "magic_link_tokens"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)

    # sha256 hex of the raw token. 64 chars. Unique because two random
    # tokens colliding has cryptographically negligible probability,
    # but the constraint catches any future bug that produces dupes.
    token_hash: str = Field(index=True, unique=True, max_length=64)

    expires_at: datetime = Field(sa_column=utc_datetime_column(index=True))
    used_at: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=utc_datetime_column(index=True),
    )

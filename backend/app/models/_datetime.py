"""Helpers for timezone-aware UTC datetime fields across all SQLModel tables.

The system rule (see docs/superpowers/specs/tz-aware-datetimes.md):
  - Every datetime is timezone-aware UTC.
  - DB columns are TIMESTAMP WITH TIME ZONE (PostgreSQL TIMESTAMPTZ).
  - Default factories return tz-aware values.
  - Naive datetimes are forbidden anywhere in the system.

Use `utc_now` as the default_factory for created_at / updated_at fields,
and `utc_datetime_column(...)` to declare the SQLAlchemy column type.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime


def utc_now() -> datetime:
    """Tz-aware UTC datetime, replacing the deprecated `datetime.utcnow()`."""
    return datetime.now(timezone.utc)


def utc_datetime_column(*, nullable: bool = False, index: bool = False) -> Column:
    """Build a SQLAlchemy Column for a tz-aware UTC datetime.

    A fresh Column instance must be created per Field — never share one
    across model declarations.
    """
    return Column(DateTime(timezone=True), nullable=nullable, index=index)


def aware_utc(value):
    """Coerce a possibly-naive datetime to tz-aware UTC. Passes None through.

    The system rule is "every datetime is tz-aware UTC", but some DB drivers
    (notably aiosqlite) drop tzinfo on read even when the column is declared
    `DateTime(timezone=True)`. PostgreSQL preserves it correctly. This helper
    is a defence-in-depth at compare/diff sites: naive values are assumed to
    be UTC (per the rule), aware values are normalised to UTC.

    Use it whenever you compare a datetime that round-tripped through the DB
    against a freshly-constructed aware datetime — without it, a SQLite
    in-memory test can silently disagree with a Postgres production deploy.
    """
    from datetime import timezone

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

"""In-process per-account login throttle.

Complements nginx's coarse per-IP rate limit with a per-email guard so a
technically-minded peer can't grind a known friend's password (they share a
NAT/Cloudflare path, so a per-IP limit alone is weak). After MAX_FAILURES
failures within WINDOW, the account is locked for LOCKOUT; a successful login
clears the counter.

State is in-process — correct for the single-worker deployment and sufficient
for this threat model (an attacker can't reset it; a server restart clearing it
is acceptable). No DB schema needed.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models._datetime import utc_now

MAX_FAILURES = 5
WINDOW = timedelta(minutes=15)
LOCKOUT = timedelta(minutes=15)


@dataclass
class _Attempts:
    count: int = 0
    window_start: datetime | None = None
    locked_until: datetime | None = None


_state: dict[str, _Attempts] = {}


def seconds_locked(email: str) -> float | None:
    """Remaining lockout seconds for this email, or None if not locked."""
    rec = _state.get(email.lower())
    if rec and rec.locked_until:
        remaining = (rec.locked_until - utc_now()).total_seconds()
        if remaining > 0:
            return remaining
    return None


def record_failure(email: str) -> None:
    """Count a failed login; lock the account once it crosses the threshold."""
    key = email.lower()
    now = utc_now()
    rec = _state.get(key)
    if rec is None or rec.window_start is None or (now - rec.window_start) > WINDOW:
        rec = _Attempts(count=0, window_start=now)
        _state[key] = rec
    rec.count += 1
    if rec.count >= MAX_FAILURES:
        rec.locked_until = now + LOCKOUT


def record_success(email: str) -> None:
    """Clear the counter after a successful login."""
    _state.pop(email.lower(), None)


def reset_throttle() -> None:
    """Clear all throttle state (test helper)."""
    _state.clear()

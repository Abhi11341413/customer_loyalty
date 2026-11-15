"""Time helpers: timestamps are ISO-8601 UTC strings (blueprint section 4.1).

Owner: M4.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def utcnow_iso() -> str:
    return utcnow().isoformat(timespec="microseconds")

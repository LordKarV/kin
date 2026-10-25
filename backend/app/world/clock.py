"""World clock: real UTC time plus a process-wide offset (set by /api/dev/clock)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from app.config import get_settings

MAX_OFFSET_DAYS = 3650
_offset_days: float = float(get_settings().clock_offset_days)


def now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=_offset_days)


def offset_days() -> float:
    return _offset_days


def set_offset_days(x: float) -> None:
    """Raises ValueError outside +-MAX_OFFSET_DAYS: a NaN or huge offset breaks every now() and would let the
    third-party sweep hard-delete everything."""
    global _offset_days
    x = float(x)
    if not math.isfinite(x) or abs(x) > MAX_OFFSET_DAYS:
        raise ValueError(f"clock offset out of range: {x}")
    _offset_days = x

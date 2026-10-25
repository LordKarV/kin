"""Common-ground model: knowledge tracing with forgetting. Pure, no DB.

p decays toward P_FLOOR with a per-item half-life; each exposure is a BKT learning transition at a rate set by its
evidence type; "asked" is a BKT incorrect observation. Half-life grows at most once per distinct UTC day.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

P_FLOOR = 0.02
PRIOR = 0.02  # any item with no row (structural knowledge is a separate gate)
LEARN = {"heard": .70, "shown": .50, "said": .95, "authored": .95, "confirmed": .98}
H0_DAYS = {"heard": 30, "shown": 21, "said": 60, "authored": 60, "confirmed": 90, "asked": 30}
GROWTH, H_MAX = 1.5, 365
FORGOT = 0.35  # reminder below this
# Known limit: no hysteresis band around FORGOT; a shown card lifts p to ~0.89. Add one if the eval sweep shows flicker.
SLIP, GUESS = 0.05, 0.02  # for "asked"

_COUNTER = {"heard": "n_heard", "shown": "n_shown", "said": "n_said", "authored": "n_said",
            "confirmed": "n_confirmed", "asked": "n_asked"}


@dataclass(frozen=True)
class State:
    p: float
    half_life_days: float
    first_at: datetime
    last_at: datetime
    last_day: str
    n_heard: int = 0
    n_shown: int = 0
    n_said: int = 0
    n_confirmed: int = 0
    n_asked: int = 0


def p_now(st: State | None, t: datetime) -> float:
    if st is None:
        return PRIOR
    dt = max(0.0, (t - st.last_at).total_seconds() / 86400)
    return P_FLOOR + (st.p - P_FLOOR) * 2 ** (-dt / st.half_life_days)


def update(st: State | None, ev: str, t: datetime) -> State:
    """Return a new State after evidence `ev` at time `t`; never mutates `st`. Raises KeyError on unknown `ev`."""
    counter = _COUNTER[ev]
    if st is not None and t < st.last_at:
        t = st.last_at  # out-of-order evidence (late apply/SMS): never move the decay anchor backwards
    p0 = p_now(st, t)
    day = t.date().isoformat()  # t is timezone-aware UTC (world/clock.now)
    if ev == "asked":
        p = p0 * SLIP / (p0 * SLIP + (1 - p0) * (1 - GUESS))
        h = float(H0_DAYS["asked"])
    else:
        p = p0 + (1 - p0) * LEARN[ev]
        if st is None:
            h = float(H0_DAYS[ev])
        elif day != st.last_day:
            h = min(H_MAX, max(st.half_life_days, H0_DAYS[ev]) * (1 + GROWTH * p0))
        else:
            h = max(st.half_life_days, H0_DAYS[ev])  # same day: no growth
    base = st or State(p, h, t, t, day)
    return replace(base, p=p, half_life_days=h, last_at=t, last_day=day, **{counter: getattr(base, counter) + 1})


def decide(st: State | None, t: datetime, structural: bool) -> str | None:
    """None | "new" | "reminder"."""
    if structural:
        return None
    if st is None:
        return "new"
    return "reminder" if p_now(st, t) < FORGOT else None

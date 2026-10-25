"""ARCHITECTURE section 4 worked demo numbers, to 3 decimals."""
import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from app.world.knowledge import FORGOT, State, decide, p_now, update

T0 = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)


def heard_once(days_ago: float, now: datetime) -> State:
    return update(None, "heard", now - timedelta(days=days_ago))


def test_never_heard_is_new():
    assert round(p_now(None, T0), 3) == 0.020
    assert decide(None, T0, structural=False) == "new"


def test_priya_six_days():
    st = heard_once(6, T0)
    assert round(p_now(st, T0), 3) == 0.617
    assert decide(st, T0, False) is None


def test_arjun_call_two_sequence():
    st = heard_once(42, T0)
    assert round(p_now(st, T0), 3) == 0.280
    assert decide(st, T0, False) == "reminder"
    shown = update(st, "shown", T0)
    assert round(shown.p, 3) == 0.640 and round(shown.half_life_days, 1) == 42.6
    heard = update(shown, "heard", T0 + timedelta(seconds=2))
    assert round(heard.p, 3) == 0.892 and round(heard.half_life_days, 1) == 42.6
    assert heard.n_shown == 1 and heard.n_heard == 2
    nxt = heard.last_at + timedelta(days=1)
    assert round(p_now(heard, nxt), 3) == 0.878
    assert decide(heard, nxt, False) is None


def test_same_day_no_growth():
    st = None
    for i in range(5):
        st = update(st, "heard", T0 + timedelta(minutes=i))
    assert st.half_life_days == 30 and st.n_heard == 5


def test_asked_lowers_p():
    old = heard_once(42, T0)
    st = update(old, "asked", T0)
    assert st.p < p_now(old, T0) and st.p < 0.1 and st.half_life_days == 30 and st.n_asked == 1
    assert update(None, "asked", T0).p < 0.1


def test_decide_structural_and_reminder():
    assert decide(None, T0, structural=True) is None
    assert decide(heard_once(42, T0), T0, structural=True) is None
    low = State(FORGOT - 0.01, 30, T0, T0, T0.date().isoformat())
    assert decide(low, T0, False) == "reminder"


def test_state_immutable():
    st = heard_once(0, T0)
    before = dataclasses.astuple(st)
    nxt = update(st, "said", T0 + timedelta(days=2))
    assert dataclasses.astuple(st) == before and nxt is not st
    assert nxt.first_at == st.first_at and nxt.n_said == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        st.p = 0.5  # type: ignore[misc]


def test_out_of_order_evidence_keeps_anchor():
    st = update(update(None, "heard", T0), "heard", T0 - timedelta(days=3))
    assert st.last_at == T0 and st.half_life_days == 30

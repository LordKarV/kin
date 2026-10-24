"""Known-value cases for standard BKT (p_init=0.1, p_learn=0.2, p_slip=0.1, p_guess=0.2)."""
import pytest
from app.fade.bkt import BKT, DEFAULT


def test_defaults_match_plan():
    assert (DEFAULT.p_init, DEFAULT.p_learn, DEFAULT.p_slip, DEFAULT.p_guess) == (0.1, 0.2, 0.1, 0.2)


def test_correct_observation_known_value():
    # posterior = .1*.9 / (.1*.9 + .9*.2) = 1/3 ; then learn: 1/3 + 2/3*.2 = 0.4667
    assert BKT().update(0.1, correct=True) == pytest.approx(0.46667, abs=1e-4)


def test_incorrect_observation_known_value():
    # posterior = .1*.1 / (.1*.1 + .9*.8) = 0.01370 ; learn → 0.2110
    assert BKT().update(0.1, correct=False) == pytest.approx(0.21096, abs=1e-4)


def test_exposure_counts_weakly():
    # exposure is a learning opportunity without an observation, at the weak rate (0.05)
    assert BKT().expose(0.1) == pytest.approx(0.145, abs=1e-6)
    assert BKT().expose(0.1) < BKT().update(0.1, correct=True)


def test_mastery_converges_and_stays_bounded():
    p = 0.1
    for _ in range(10):
        p = BKT().update(p, correct=True)
    assert 0.99 < p <= 1.0
    for _ in range(100):
        p = BKT().expose(p)
    assert p <= 1.0

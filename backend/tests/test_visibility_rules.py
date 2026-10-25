"""Truth tables for ARCHITECTURE 1.3 visibility and disclosure predicates."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.world import clock
from app.world.visibility import FactV, bridge_candidate, content_ok, disclosable, fact_visible, usable

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
ARJUN, MEI, PRIYA, LIN = 1, 2, 3, 17


def fact(**kw) -> FactV:
    base = FactV(id=1, subject_id=MEI, speaker_id=MEI, predicate="did", text="started bouldering",
                 keys=(("bouldering", "攀岩"),), status="active", sensitive_kind="", remembered=False,
                 shareable=True, third_party=False, expires_at=None, pinned=False, storyline_id=None,
                 said_at=NOW - timedelta(days=1), refs=frozenset())
    return replace(base, **kw)


def test_fact_visible():
    aud = frozenset({MEI, ARJUN})
    assert fact_visible(fact(), aud, ARJUN, NOW)
    assert not fact_visible(fact(), aud, PRIYA, NOW)
    past = NOW - timedelta(seconds=1)
    assert not fact_visible(fact(expires_at=past), aud, ARJUN, NOW)
    assert not fact_visible(fact(expires_at=NOW), aud, ARJUN, NOW)
    assert fact_visible(fact(expires_at=past, pinned=True), aud, ARJUN, NOW)
    assert fact_visible(fact(expires_at=NOW + timedelta(days=1)), aud, ARJUN, NOW)


def test_content_ok():
    assert content_ok(fact())
    assert not content_ok(fact(sensitive_kind="health"))
    assert content_ok(fact(sensitive_kind="health", remembered=True))


def test_disclosable():
    ident = fact(predicate="lives_in", text="lives in Shanghai")
    none = frozenset()
    assert disclosable(ident, MEI, none, NOW)
    assert not disclosable(ident, ARJUN, none, NOW)  # speaker-only
    assert not disclosable(replace(ident, shareable=False), MEI, none, NOW)
    assert not disclosable(fact(), MEI, none, NOW)  # "did" is not IDENTITY
    assert not disclosable(replace(ident, sensitive_kind="money"), MEI, none, NOW)
    assert not disclosable(replace(ident, status="superseded"), MEI, none, NOW)
    assert not disclosable(replace(ident, expires_at=NOW - timedelta(days=1)), MEI, none, NOW)
    # Mei's fact about Lin: only when Lin was just mentioned
    about_lin = replace(ident, subject_id=LIN, predicate="tie", third_party=True)
    assert not disclosable(about_lin, MEI, none, NOW)
    assert disclosable(about_lin, MEI, frozenset({LIN}), NOW)
    assert not disclosable(replace(about_lin, speaker_id=ARJUN), MEI, frozenset({LIN}), NOW)  # Arjun's claim about Lin is never Mei's to disclose
    # owner raising their own storyline: any predicate
    assert disclosable(fact(predicate="state", storyline_id=5), MEI, none, NOW)
    # third-party claim (Arjun said it) about Mei's storyline stays private
    assert not disclosable(fact(predicate="state", storyline_id=5, speaker_id=ARJUN), MEI, none, NOW)
    # someone else's storyline raised by Mei: not owner, and "state" is not IDENTITY
    assert not disclosable(fact(predicate="state", storyline_id=5, subject_id=ARJUN), MEI, frozenset({ARJUN}), NOW)


def test_usable():
    aud = frozenset({MEI, ARJUN})
    ident = fact(predicate="lives_in")
    assert usable(fact(), aud, ARJUN, None, frozenset(), NOW)
    assert not usable(fact(), aud, PRIYA, None, frozenset(), NOW)
    assert usable(ident, aud, PRIYA, MEI, frozenset(), NOW)  # disclosed by the speaker
    assert not usable(fact(sensitive_kind="conflict"), aud, ARJUN, None, frozenset(), NOW)


def test_bridge_candidate():
    assert bridge_candidate(fact(), frozenset({MEI}), MEI, PRIYA, NOW)
    assert not bridge_candidate(fact(subject_id=ARJUN), frozenset({MEI}), MEI, PRIYA, NOW)  # non-self
    assert not bridge_candidate(fact(speaker_id=ARJUN), frozenset({MEI}), MEI, PRIYA, NOW)  # said by someone else
    assert not bridge_candidate(fact(), frozenset({MEI, PRIYA}), MEI, PRIYA, NOW)  # other already heard
    assert not bridge_candidate(fact(status="resolved"), frozenset({MEI}), MEI, PRIYA, NOW)
    assert not bridge_candidate(fact(sensitive_kind="health"), frozenset({MEI}), MEI, PRIYA, NOW)
    assert bridge_candidate(fact(shareable=False), frozenset({MEI}), MEI, PRIYA, NOW)  # SMS facts still nudge


def test_third_party_ttl_with_world_clock():
    ttl = get_settings().third_party_ttl_days
    assert ttl > 42  # the demo's six-week gap must not expire the Lin fact (D11)
    said = clock.now()
    f = fact(third_party=True, subject_id=LIN, said_at=said, expires_at=said + timedelta(days=ttl))
    aud = frozenset({MEI, ARJUN})
    orig = clock.offset_days()
    try:
        clock.set_offset_days(orig + 42)
        assert fact_visible(f, aud, ARJUN, clock.now())
        clock.set_offset_days(orig + ttl + 1)
        assert not fact_visible(f, aud, ARJUN, clock.now())
        assert fact_visible(replace(f, pinned=True), aud, ARJUN, clock.now())
    finally:
        clock.set_offset_days(orig)


def test_clock_offset_validation():
    orig = clock.offset_days()
    try:
        clock.set_offset_days(3)
        assert clock.offset_days() == 3.0
        assert clock.now().tzinfo is not None and clock.now().utcoffset() == timedelta(0)
        for bad in (float("nan"), float("inf"), 1e9, -3651):
            with pytest.raises(ValueError):
                clock.set_offset_days(bad)
        assert clock.offset_days() == 3.0
    finally:
        clock.set_offset_days(orig)

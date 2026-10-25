"""The common-ground eval stays runnable offline (ARCHITECTURE 11); the naive baseline is scored like KIN."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import eval.run_cg as cg
from app import config
from app import llm as llm_mod
from eval.common_ground.schemas import load_scenarios
from eval.run_cg import KIN_EXIT, Pred, naive_decide, naive_system, render_user_message, score

ROOT = Path(__file__).resolve().parents[1]


def test_run_cg_limit_10_exits_0_with_tables(tmp_path):
    out = tmp_path / "cg.md"
    r = subprocess.run([sys.executable, "-m", "eval.run_cg", "--limit", "10", "--out", str(out)], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    md = out.read_text()
    assert "| Metric |" in md and "| Hard fails |" in md and "synthetic 500 people" in md
    assert "| Gap (who/what) precision | n/a" not in md  # KIN produced and scored real cards


class FakeLLM:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def text(self, system, user, **kw):
        self.calls.append((system, user, kw))
        return self.replies.pop(0)


def _demo():
    return next(s for s in load_scenarios() if s.id == "lin_six_weeks")


def test_naive_reply_is_parsed_and_scored_with_the_same_code():
    sc = _demo()
    reply = {"mei": {"cards": []}, "priya": {"cards": []},
             "arjun": {"cards": [{"kind": "who", "key": "lin", "gap": "new", "cites": []},
                                 {"kind": "bridge", "key": "boulder", "gap": None, "cites": []}]}}
    llm = FakeLLM("```json\n" + json.dumps(reply) + "\n```")
    run = naive_decide(sc, llm, naive_system())
    system, user, kw = llm.calls[0]
    assert kw["reasoning_effort"] == "minimal" and "CARD KINDS" in system and "CALL NOW (day 42)" in user
    assert user == render_user_message(sc.model_dump(mode="json"))  # deterministic bytes
    c = score(sc, run.preds).c
    assert (c["entity_tp"], c["bridge_tp"], c["gap_total"], c["gap_ok"]) == (1, 1, 1, 0)  # "new" is the wrong gap
    assert run.parse_failures == 0


def test_naive_bad_json_twice_is_a_counted_failure_and_leaks_are_hard_fails():
    sc = _demo()
    run = naive_decide(sc, FakeLLM("not json", '{"arjun": 3}'), naive_system())
    assert run.parse_failures == 1 and all(v == [] for v in run.preds.values())
    leak = {"arjun": [], "mei": [],
            "priya": [p for p in naive_decide(sc, FakeLLM(json.dumps(
                {"priya": {"cards": [{"kind": "bridge", "key": "boulder", "gap": None, "cites": ["boulder", "x"]}]}})),
                naive_system()).preds["priya"]]}
    c = score(sc, leak).c
    assert (c["non_self_bridge"], c["sms_leak"], c["hallucinated_cite"]) == (1, 1, 1)


@pytest.fixture
def in_process(monkeypatch):
    """main() sets env and patches LLM.structured globally; record the originals so teardown restores them."""
    for k in ("BRIDGE_RERANK", "SEED_DEMO_FAMILY", "MODEL_API_KEY", "DATABASE_URL"):
        monkeypatch.setenv(k, os.environ.get(k, ""))
    monkeypatch.setenv("BRIDGE_RERANK", "0")
    monkeypatch.setenv("SEED_DEMO_FAMILY", "0")
    monkeypatch.setattr(llm_mod.LLM, "structured", cg._blocked)
    config.get_settings.cache_clear()
    llm_mod.reset_llm()
    yield
    config.get_settings.cache_clear()
    llm_mod.reset_llm()


def test_kin_side_scores_the_demo_scenario(in_process, tmp_path):
    kin, nv, partial, _ = cg.run_set([_demo()], tmp_path, None, "")
    assert nv is None and partial
    assert kin.c["entity_tp"] >= 1 and kin.c["bridge_tp"] == 1
    assert all(kin.c[h] == 0 for h in KIN_EXIT)


def test_hard_fail_makes_main_exit_1(in_process, tmp_path, monkeypatch):
    real = cg.score

    def leaky(*a, **kw):
        sco = real(*a, **kw)
        sco.c["sms_leak"] += 1
        return sco

    monkeypatch.setattr(cg, "score", leaky)
    assert cg.main(["--limit", "1", "--out", str(tmp_path / "cg.md")]) == 1


def test_sms_text_in_a_card_body_is_a_leak_even_without_a_cite():
    sc = _demo()
    sms = next(f for f in sc.facts if f.source == "sms")
    other = next(k for k in sc.probe.participants if k not in (sms.speaker, sc.probe.speaker))
    seen = Pred("entity", "lin", "reminder", (), "who", f"Lin. Also, {sms.text}.")
    assert score(sc, {other: [seen]}).c["sms_leak"] == 1

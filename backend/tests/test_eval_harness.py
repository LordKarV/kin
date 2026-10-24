"""The eval must stay runnable offline (--mock scores the linker-only rendering)."""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_run_eval_mock_writes_results(tmp_path):
    out = tmp_path / "results.md"
    r = subprocess.run([sys.executable, "-m", "eval.run_eval", "--mock", "--limit", "20", "--out", str(out)], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    md = out.read_text()
    assert "| Condition |" in md and "linker-only" in md and "Idiom cards" in md


def test_fallback_rows_score_as_errors_and_generic_gets_context():
    from eval.run_eval import score_row
    from app.mt.translate import TranslateResult, Translator, GENERIC_RULES
    from app.mt.schemas import TranslationOut
    out = TranslationOut(translation="your uncle Ravi mama (Mom's younger brother) called", grounded_spans=[], pragmatics_cards=[], passthrough_kept=[], confidence=0.3)
    res = TranslateResult(out, [], [], {"mt_ms": 1.0}, error="RateLimitError: 429")
    from eval.schemas import GroundingItem
    it = GroundingItem(id="x", category="kin", src_text="உன் மாமா", src_roman="un mama", gloss="", entities=[{"source": "மாமா", "node": "p_ravi_mama", "type": "person", "must_include": [["Ravi"]]}])
    row = score_row(it, res)
    assert row["entities"][0]["correct"] is False and row["error"]
    assert "Speaker" in Translator.generic_user_prompt(it.src_text, "Kamala", "Arjun", ["Un mama nethu phone pannaan."])

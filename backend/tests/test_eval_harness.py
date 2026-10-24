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

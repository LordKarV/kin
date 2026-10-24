"""Generic vs grounded eval on the Phase 1 test sets. `python -m eval.run_eval [--mock] [--limit N] [--out eval/results.md]`

Conditions:
  generic      same model, no family context (baseline)
  grounded     linker + family roster + structured output (KIN)
  linker-only  deterministic fallback rendering, no LLM (always runs; this is the floor and the offline CI check)
Metrics: entity error rate (overall / kin / name-collision / dish-place), kin-term flattening rate, idiom card P/R, latency p50/p95.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.db.seed import seed_demo_family
from app.db.session import init_db, session_scope
from app.graph.kinship import FamilyGraph
from app.mt.translate import Translator
from eval.schemas import GroundingItem, IdiomItem

HERE = Path(__file__).resolve().parent
RAVIS = {"p_ravi_mama", "p_ravi_periyappa"}


def _norm(s: str) -> str:
    return re.sub(r"[^\w\s']", " ", s.lower())


def _contains(hay: str, needle: str) -> bool:
    return _norm(needle).strip() in _norm(hay)


def load_items(limit: int | None):
    g = [GroundingItem.model_validate(json.loads(l)) for l in (HERE / "testset" / "kinship_names_dishes.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    i = [IdiomItem.model_validate(json.loads(l)) for l in (HERE / "testset" / "idioms.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if limit:
        g, i = g[:limit], i[:limit]
    return g, i


def score_entity(e, rendered_by_node: dict[str, str], translation: str) -> tuple[bool, bool]:
    """→ (correct, flattened). Text searched = the span rendered for that node (if any) + the spoken translation."""
    text = f"{rendered_by_node.get(e.node, '')} {translation}"
    correct = all(any(_contains(text, alt) for alt in group) for group in e.must_include)
    flattened = (not correct) and any(_contains(translation, bad) for bad in e.must_not_include)
    return correct, flattened


def score_row(it: GroundingItem, res) -> dict:
    """Score one item. A provider failure (fallback or empty output) counts as WRONG for every entity in both conditions,
    so the grounded condition cannot ride its linker-only fallback past a 429 that the generic condition cannot survive."""
    rendered = {s.node_id: s.rendered for s in res.result.grounded_spans}
    ents = []
    for e in it.entities:
        ok, flat = score_entity(e, rendered, res.result.translation)
        if res.error:
            ok, flat = False, False
        ents.append({"source": e.source, "node": e.node, "type": e.type, "correct": ok, "flattened": flat})
    return {"id": it.id, "category": it.category, "translation": res.result.translation, "entities": ents,
            "latency_ms": res.latencies.get("mt_ms", 0.0), "error": res.error, "cards": len(res.result.pragmatics_cards)}


def run_condition(name: str, items: list[GroundingItem], fn, workers: int) -> dict:
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(lambda it: score_row(it, fn(it)), items))

    def err_rate(pred):
        es = [e for r in rows if pred(r) for e in r["entities"]]
        return (1 - sum(e["correct"] for e in es) / len(es)) if es else float("nan"), len(es)

    kin_es = [e for r in rows if r["category"] == "kin" for e in r["entities"] if e["type"] == "person"]
    flat = sum(e["flattened"] for e in kin_es) / len(kin_es) if kin_es else float("nan")
    coll = [e for r in rows if r["category"] == "name_collision" for e in r["entities"] if e["node"] in RAVIS]
    coll_err = (1 - sum(e["correct"] for e in coll) / len(coll)) if coll else float("nan")
    lats = sorted(r["latency_ms"] for r in rows)
    p = lambda q: lats[min(len(lats) - 1, int(q * len(lats)))] if lats else float("nan")  # noqa: E731
    return {"name": name, "rows": rows, "overall": err_rate(lambda r: True), "kin": err_rate(lambda r: r["category"] == "kin"),
            "collision": (coll_err, len(coll)), "dish_place": err_rate(lambda r: r["category"] == "dish_place"), "flattening": flat,
            "p50": p(0.5), "p95": p(0.95), "errors": sum(1 for r in rows if r["error"])}


def run_idioms(name: str, items: list[IdiomItem], fn, workers: int) -> dict:
    with ThreadPoolExecutor(max_workers=workers) as ex:
        preds = list(ex.map(lambda it: len(fn(it).result.pragmatics_cards) > 0, items))
    tp = sum(1 for it, p in zip(items, preds) if it.expect_card and p)
    fp = sum(1 for it, p in zip(items, preds) if not it.expect_card and p)
    fn_ = sum(1 for it, p in zip(items, preds) if it.expect_card and not p)
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn_) if tp + fn_ else float("nan")
    return {"name": name, "precision": prec, "recall": rec, "tp": tp, "fp": fp, "fn": fn_, "n": len(items)}


def pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.0f}%"


def write_results(path: Path, conds: list[dict], idioms: list[dict], model: str, mock: bool) -> None:
    lines = [f"# KIN eval results", "", f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · model `{model}` · {'MOCK (no LLM)' if mock else 'live'}", "",
             "## Entity grounding (error rate, lower is better)", "",
             "| Condition | Overall | Kin terms | Name collisions | Dishes/places | Kin flattening | MT p50 | MT p95 | API errors |",
             "|---|---|---|---|---|---|---|---|---|"]
    for c in conds:
        lines.append(f"| {c['name']} | {pct(c['overall'][0])} (n={c['overall'][1]}) | {pct(c['kin'][0])} (n={c['kin'][1]}) | {pct(c['collision'][0])} (n={c['collision'][1]}) | "
                     f"{pct(c['dish_place'][0])} (n={c['dish_place'][1]}) | {pct(c['flattening'])} | {c['p50']:.0f} ms | {c['p95']:.0f} ms | {c['errors']} |")
    lines += ["", "## Idiom cards", "", "| Condition | Precision | Recall | TP | FP | FN | n |", "|---|---|---|---|---|---|---|"]
    for i in idioms:
        lines.append(f"| {i['name']} | {pct(i['precision'])} | {pct(i['recall'])} | {i['tp']} | {i['fp']} | {i['fn']} | {i['n']} |")
    for c in conds:
        misses = [(r["id"], e["source"], e["node"], r["translation"][:90]) for r in c["rows"] for e in r["entities"] if not e["correct"]]
        if misses:
            lines += ["", f"<details><summary>{c['name']}: {len(misses)} misses</summary>", "", "| item | span | expected node | output |", "|---|---|---|---|"]
            lines += [f"| {i} | {s} | {n} | {t.replace('|', '/')} |" for i, s, n, t in misses[:40]]
            lines += ["", "</details>"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="no LLM: score the linker-only rendering")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(HERE / "results.md"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--effort", default="medium", help="reasoning_effort for eval calls")
    args = ap.parse_args(argv)

    init_db()
    with session_scope() as s:
        fam = seed_demo_family(s)
        graph = FamilyGraph.from_session(s, fam.id)
    tr = Translator(graph)
    g_items, i_items = load_items(args.limit)
    settings = get_settings()

    def linker_only(it: GroundingItem):
        from app.mt.translate import TranslateResult
        t0 = time.perf_counter()
        spans = tr.linker.link(it.src_text, it.speaker, it.listener, context=it.context)
        out = tr.fallback(it.src_text, spans)
        return TranslateResult(out, spans, [], {"mt_ms": (time.perf_counter() - t0) * 1000})

    conds = [run_condition("linker-only (no LLM)", g_items, linker_only, args.workers)]
    idioms: list[dict] = []
    if not args.mock:
        if not settings.model_api_key:
            print("MODEL_API_KEY is not set; run with --mock or fill .env", file=sys.stderr)
            return 2
        hist = lambda it: [(it.speaker, c, "") for c in it.context]  # noqa: E731
        conds.append(run_condition("generic (same model + same context, no family graph)", g_items,
                                   lambda it: tr.translate_generic(it.src_text, reasoning_effort=args.effort, speaker=it.speaker, listener=it.listener, history=hist(it)), args.workers))
        conds.append(run_condition("grounded (KIN)", g_items, lambda it: tr.translate(it.src_text, it.speaker, it.listener, history=hist(it), reasoning_effort=args.effort), args.workers))
        idioms.append(run_idioms("generic", i_items, lambda it: tr.translate_generic(it.src_text, reasoning_effort=args.effort, speaker="p_kamala", listener="p_arjun"), args.workers))
        idioms.append(run_idioms("grounded (KIN)", i_items, lambda it: tr.translate(it.src_text, "p_kamala", "p_arjun", reasoning_effort=args.effort), args.workers))
    else:
        idioms.append({"name": "linker-only (no cards in mock)", "precision": float("nan"), "recall": float("nan"), "tp": 0, "fp": 0, "fn": sum(1 for i in i_items if i.expect_card), "n": len(i_items)})

    out = Path(args.out)
    write_results(out, conds, idioms, settings.llm_model, args.mock)
    print(out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

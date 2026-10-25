"""Draft a kinship table for every Muse Voice Transcribe language except the hand-written gold one, with Muse Spark.
Run from repo root: backend/.venv/bin/python scripts/make_kin_tables.py [codes...]   (needs MODEL_API_KEY)
Each draft is validated by app.graph.kin_tables on load and stays verified=false until a speaker reviews it."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.graph.kin_tables import DIR, GRAMMAR_DOC, MUSE_LANGUAGES, LanguageTableOut, _tamil, load_table  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.llm import LLM  # noqa: E402

SYSTEM = f"""You are a kinship-terminology lexicographer. Produce a kinship table for the requested language for a family-aware
live interpreter. {GRAMMAR_DOC}
Requirements:
- 20 to 40 `terms`, kind "kin": mother, father, grandparents (both sides if the language distinguishes), parents' siblings (all
  distinctions the language makes: maternal/paternal, elder/younger, by marriage), siblings (elder/younger if distinguished),
  children, grandchildren, in-laws (parents-in-law, son/daughter-in-law, siblings-in-law), cousins if there is a word, spouse.
- Also 2-6 entries of kind "endearment" or "honorific" (terms of affection for a child, respectful address particles) with patterns [].
- `term` is the romanized/ASCII lowercase canonical form; `script` the native form; `variants` other spellings and romanizations.
- Patterns must use ONLY the allowed step words, from the speaker to the relative. A term used for several relatives lists several patterns.
- Fill the morphology fields honestly for THIS language; use [] when a field does not apply (e.g. no case suffixes in Mandarin or Vietnamese).
- Output JSON only, matching the schema."""


def main(codes: list[str]) -> None:
    st = get_settings()
    llm = LLM(api_key=st.model_api_key, backup_api_key=st.model_api_key_backup, base_url=st.llm_base_url, model=st.llm_model, timeout_s=300)
    example = _tamil().to_json()
    example["terms"] = example["terms"][:6]
    DIR.mkdir(exist_ok=True)
    for code in codes:
        name = MUSE_LANGUAGES[code]
        user = f"Language: {name} (code {code}).\nHere is the hand-written Tamil table as a format example (do NOT copy its content):\n{json.dumps(example, ensure_ascii=False)}"
        out = None
        for attempt in range(2):
            try:
                out = llm.structured(LanguageTableOut, SYSTEM, user, reasoning_effort="medium", max_completion_tokens=16000)
                break
            except Exception as e:  # noqa: BLE001
                print(f"{code}: attempt {attempt + 1} failed: {type(e).__name__}: {str(e)[:120]}", flush=True)
        if out is None:
            continue
        data = out.model_dump()
        data.update({"code": code, "name": name, "verified": False, "source": llm.model, "notes": "Draft by Muse Spark; review by a native speaker before relying on it."})
        (DIR / f"{code}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        load_table.cache_clear()
        t = load_table(code)
        print(f"{code} {name}: {len(t.terms)} terms kept, {len(t.dropped)} dropped, {llm.last_latency_ms:.0f} ms", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or [c for c in sorted(MUSE_LANGUAGES) if c != "ta"])

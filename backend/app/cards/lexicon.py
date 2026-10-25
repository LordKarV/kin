"""Per-heritage-language cultural lexicon (foods, festivals, rituals, places, address forms, sayings, objects).

Nothing is hand-seeded per family. A language's lexicon is drafted ONCE by Muse Spark and cached as reference data in
app/cards/lexicons/<lang>.json (verified=false until a speaker reviews it, like app/graph/kin_tables). Entries are
validated on load; bad ones are dropped and counted. The family's own learned items (past glossary cards) are added at
match time by app/cards/glance.py so a term explained once is instant forever after.

CLI: python -m app.cards.lexicon ta hi
"""
from __future__ import annotations

import json
import logging
import re
import sys
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from ..graph.kin_tables import MUSE_LANGUAGES

log = logging.getLogger("kin.cards.lexicon")
DIR = Path(__file__).resolve().parent / "lexicons"
CATEGORIES = ("food", "festival", "ritual", "place", "address", "saying", "object", "other")
MAX_FORMS = 16
MAX_FORM_LEN = 120
GEN_TIMEOUT_S = 300.0       # 12k-token structured outputs take minutes; the live client's 20 s timeout would cut them off
GEN_MAX_TOKENS = 12000      # reasoning tokens count against this budget (DECISIONS 2026-10-24)

# one Muse call per batch; categories grouped so each batch stays ~40-50 entries
BATCHES = [
    (("food",), 50, "everyday home dishes, snacks, sweets, drinks and ingredients a grandparent would mention"),
    (("festival", "ritual"), 45, "festivals, religious and life-cycle rituals, temple and household customs"),
    (("place", "object", "other"), 45, "places that carry cultural meaning (temples, towns, the native village idea, markets) and culturally specific objects or clothing"),
    (("address", "saying"), 45, "non-kin address forms and honorifics (NOT kinship terms like mother/uncle, those live elsewhere), plus common sayings, proverbs and idioms"),
]


class EntryOut(BaseModel):
    key: str = Field(description="short ASCII snake_case id, unique in this language, e.g. 'pongal_dish'")
    forms: list[str] = Field(description="surface forms as heard: native script AND common romanizations, including common inflected/case-suffixed forms")
    translate_as: str = Field(description="how to render it in English in a translation (keep the word if English speakers use it)")
    category: str = Field(description="one of: " + ", ".join(CATEGORIES))
    note: str = Field(description="ONE line: why it matters to a grandchild hearing it")
    wiki_title: str = Field(description="exact English Wikipedia article title for a picture, or '' if none is a good match")


class LexiconBatchOut(BaseModel):
    entries: list[EntryOut]


SYSTEM = """You build a cultural glossary for a family-call interpreter. A grandparent speaks {name}; a grandchild who grew up in English listens.
List words and phrases the grandparent is likely to say that a literal translation would flatten: {focus}.
Rules:
- Categories allowed in this batch: {cats}. Produce about {n} entries.
- forms: the native-script spelling first, then 1-4 common romanizations, then common inflected forms (case suffixes, plurals) in both scripts. No English-only forms.
- Do NOT include kinship terms (mother, grandmother, uncle, ...).
- note is one short line on why it matters. translate_as is a short English rendering.
- wiki_title must be a real English Wikipedia article title you are confident exists, else ''. Sayings usually get ''.
Output JSON matching the schema."""


@dataclass(frozen=True)
class LexEntry:
    key: str
    forms: tuple[str, ...]
    translate_as: str
    category: str
    note: str
    wiki_title: str = ""

    @property
    def native(self) -> str:
        return next((f for f in self.forms if re.search(r"[^\x00-\x7f]", f)), "")


@dataclass
class Lexicon:
    lang: str
    entries: list[LexEntry]
    verified: bool = False
    source: str = ""
    generated_at: str = ""
    dropped: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {c: sum(1 for e in self.entries if e.category == c) for c in CATEGORIES}


def _mixed_script(form: str) -> bool:
    """True if the non-ASCII letters come from more than one script (first word of each letter's Unicode name)."""
    scripts = {unicodedata.name(c, "?").split()[0] for c in form if ord(c) > 0x7F and unicodedata.category(c)[0] in "LM"}
    return len(scripts) > 1


def validate_entries(raw: list[dict]) -> tuple[list[LexEntry], list[str]]:
    """Mechanical validation: drop entries with no key/forms/meaning or an unknown category; dedupe keys and forms."""
    out: list[LexEntry] = []
    dropped: list[str] = []
    keys: set[str] = set()
    for r in raw:
        if not isinstance(r, dict):
            dropped.append(f"not an object: {str(r)[:40]}")
            continue
        key = re.sub(r"[^a-z0-9_]+", "_", str(r.get("key") or "").strip().lower()).strip("_")
        forms = [f.strip() for f in (r.get("forms") or []) if isinstance(f, str) and f.strip() and len(f.strip()) <= MAX_FORM_LEN]
        mixed = [f for f in forms if _mixed_script(f)]
        if mixed:  # Muse sometimes leaks a letter from a sister script (a letter from a sister script inside a word): drop that form
            dropped.extend(f"{r.get('key')}: mixed-script form {f!r}" for f in mixed)
            forms = [f for f in forms if f not in mixed]
        forms = list(dict.fromkeys(forms))[:MAX_FORMS]
        cat = str(r.get("category") or "").strip().lower()
        tr = str(r.get("translate_as") or "").strip()
        if not key or key in keys:
            dropped.append(f"{key or '?'}: missing or duplicate key")
        elif not forms:
            dropped.append(f"{key}: no forms")
        elif cat not in CATEGORIES:
            dropped.append(f"{key}: bad category {cat!r}")
        elif not tr:
            dropped.append(f"{key}: no translate_as")
        else:
            keys.add(key)
            out.append(LexEntry(key, tuple(forms), tr, cat, str(r.get("note") or "").strip().splitlines()[0] if r.get("note") else "",
                                str(r.get("wiki_title") or "").strip()))
    return out, dropped


_cache: dict[str, Lexicon] = {}
_lock = threading.Lock()
_gen_locks: dict[str, threading.Lock] = {}


def path_for(lang: str) -> Path:
    return DIR / f"{lang}.json"


def load_lexicon(lang: str) -> Lexicon:
    """Cached load + validation. A missing file is an empty lexicon (call ensure_lexicon to generate it)."""
    with _lock:
        if lang in _cache:
            return _cache[lang]
    p = path_for(lang)
    if not p.exists():
        return Lexicon(lang, [], source="missing")
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.error("lexicon %s unreadable: %s", p, e)
        return Lexicon(lang, [], source="unreadable")
    entries, dropped = validate_entries(j.get("entries", []))
    if dropped:
        log.info("lexicon %s: dropped %d invalid entries", lang, len(dropped))
    lex = Lexicon(lang, entries, bool(j.get("verified", False)), j.get("source", ""), j.get("generated_at", ""), dropped)
    with _lock:
        _cache[lang] = lex
    return lex


def reset_lexicon_cache() -> None:
    with _lock:
        _cache.clear()


def _default_llm():
    from ..config import get_settings
    from ..llm import LLM

    s = get_settings()
    return LLM(api_key=s.model_api_key or "missing", backup_api_key=s.model_api_key_backup, base_url=s.llm_base_url,
               model=s.llm_model, timeout_s=GEN_TIMEOUT_S)


def generate_lexicon(lang: str, llm=None) -> dict:
    """Draft a lexicon with Muse Spark, one structured call per category batch (run concurrently). Returns the file JSON."""
    if lang not in MUSE_LANGUAGES:
        raise KeyError(f"unsupported language {lang!r}")
    from ..llm import StructuredOutputError

    llm = llm or _default_llm()
    name = MUSE_LANGUAGES[lang]

    def one(batch) -> list[dict]:
        cats, n, focus = batch
        system = SYSTEM.format(name=name, focus=focus, cats=", ".join(cats), n=n)
        try:
            out = llm.structured(LexiconBatchOut, system, f"Language: {name} ({lang}). Categories: {', '.join(cats)}.",
                                 reasoning_effort="low", max_completion_tokens=GEN_MAX_TOKENS)
        except StructuredOutputError as e:
            log.error("lexicon %s batch %s failed: %s", lang, cats, e)
            return []
        return [e.model_dump() for e in out.entries if e.category in cats]

    with ThreadPoolExecutor(max_workers=len(BATCHES)) as ex:
        raw = [e for part in ex.map(one, BATCHES) for e in part]
    if not raw:
        raise RuntimeError(f"lexicon generation for {lang} produced no entries")
    return {"lang": lang, "language": name, "verified": False, "source": f"muse-spark ({getattr(llm, 'model', '?')}, effort low)",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "notes": "Muse Spark draft; not reviewed by a speaker.", "entries": raw}


def ensure_lexicon(lang: str, llm=None) -> Lexicon:
    """Load, generating and caching to disk first if missing. Thread-safe: one generation per language at a time."""
    with _lock:
        glock = _gen_locks.setdefault(lang, threading.Lock())
    with glock:
        p = path_for(lang)
        if not p.exists():
            data = generate_lexicon(lang, llm)
            DIR.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(p)
            with _lock:
                _cache.pop(lang, None)
    return load_lexicon(lang)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO)
    if not argv:
        print("usage: python -m app.cards.lexicon <lang> [<lang> ...]")
        return 2
    for lang in argv:
        lex = ensure_lexicon(lang)
        print(f"{lang}: {len(lex.entries)} entries, {len(lex.dropped)} dropped, {lex.counts()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

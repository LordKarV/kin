"""Per-language kinship tables for every Muse Voice Transcribe language (VERIFIED list of 25, dev.meta.ai/docs/speech-to-text).

A table = the language's kin terms in the resolver's pattern grammar + the small amount of morphology the fast linker
needs (script block, droppable finals, case suffixes, possessives, politeness markers). One table is hand-written (gold,
verified=True). The other 24 are Muse Spark drafts (scripts/make_kin_tables.py), validated mechanically here and flagged
verified=False until a speaker checks them. Tables live in app/graph/kin_tables/<code>.json and are seeded into the DB.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from .ontology import KIN_TERMS, KinTermDef, normalize_term

log = logging.getLogger("kin.tables")
DIR = Path(__file__).resolve().parent / "kin_tables"

MUSE_LANGUAGES = {"ar": "Arabic", "bn": "Bengali", "nl": "Dutch", "en": "English", "fr": "French", "de": "German", "he": "Hebrew", "hi": "Hindi",
                  "id": "Indonesian", "it": "Italian", "ja": "Japanese", "kn": "Kannada", "ko": "Korean", "ms": "Malay", "zh": "Mandarin Chinese",
                  "mr": "Marathi", "pl": "Polish", "pt": "Portuguese", "es": "Spanish", "tl": "Tagalog", "ta": "Tamil", "te": "Telugu", "th": "Thai",
                  "tr": "Turkish", "vi": "Vietnamese"}
NATIVE = {"ar": "العربية", "bn": "বাংলা", "nl": "Nederlands", "en": "English", "fr": "Français", "de": "Deutsch", "he": "עברית", "hi": "हिन्दी", "id": "Bahasa Indonesia",
          "it": "Italiano", "ja": "日本語", "kn": "ಕನ್ನಡ", "ko": "한국어", "ms": "Bahasa Melayu", "zh": "中文", "mr": "मराठी", "pl": "Polski", "pt": "Português",
          "es": "Español", "tl": "Tagalog", "ta": "தமிழ்", "te": "తెలుగు", "th": "ไทย", "tr": "Türkçe", "vi": "Tiếng Việt"}
# Unicode blocks for heritage-script detection ("" = Latin script, indistinguishable from English by script alone)
SCRIPT = {"ar": "[؀-ۿ]", "bn": "[ঀ-৿]", "he": "[֐-׿]", "hi": "[ऀ-ॿ]", "mr": "[ऀ-ॿ]", "ja": "[぀-ヿ一-鿿]",
          "kn": "[ಀ-೿]", "ko": "[가-힯ᄀ-ᇿ]", "zh": "[一-鿿]", "ta": "[஀-௿]", "te": "[ఀ-౿]", "th": "[฀-๿]"}
# BCP-47 locales for Twilio ConversationRelay <Language code>. VERIFY each against Twilio's voice-configuration table before a phone demo.
LOCALE = {"ar": "ar-SA", "bn": "bn-IN", "nl": "nl-NL", "en": "en-US", "fr": "fr-FR", "de": "de-DE", "he": "he-IL", "hi": "hi-IN", "id": "id-ID", "it": "it-IT",
          "ja": "ja-JP", "kn": "kn-IN", "ko": "ko-KR", "ms": "ms-MY", "zh": "zh-CN", "mr": "mr-IN", "pl": "pl-PL", "pt": "pt-BR", "es": "es-ES", "tl": "tl-PH",
          "ta": "ta-IN", "te": "te-IN", "th": "th-TH", "tr": "tr-TR", "vi": "vi-VN"}

STEP_WORDS = {"mother", "father", "parent", "spouse", "husband", "wife", "son", "daughter", "child", "brother", "sister", "sibling",
              "elder_brother", "younger_brother", "elder_sister", "younger_sister"}
GRAMMAR_DOC = ("Pattern = dot-separated steps from the speaker ('ego') to the relative, using ONLY these step words: "
               + ", ".join(sorted(STEP_WORDS)) + ". Examples: mother.brother (mother's brother), father.elder_brother, mother.mother, son.wife, "
               "spouse.father (father-in-law), parent.sibling.child (cousin), husband.younger_brother. Several patterns = context-dependent term.")


class TermOut(BaseModel):
    term: str = Field(description="romanized/ASCII lowercase canonical form (for Latin-script languages the word itself)")
    script: str = Field(description="native-script form (same as term for Latin-script languages)")
    variants: list[str] = Field(description="other spellings, romanizations, vocative/diminutive forms")
    patterns: list[str] = Field(description="relation patterns in the grammar; empty for endearments/honorifics")
    gloss: str
    kind: str = Field(description="kin | endearment | honorific")
    notes: str


class LanguageTableOut(BaseModel):
    final_strip: list[str] = Field(description="trailing characters/letters a noun drops before a suffix attaches (e.g. Tamil pulli); [] if none")
    suffixes: list[str] = Field(description="common case/clitic suffixes attached to nouns in the native script, longest first; [] for isolating languages")
    roman_suffixes: list[str] = Field(description="the same suffixes as commonly romanized (ASCII); [] if the script is Latin or not romanized")
    possessive_speaker: list[str] = Field(description="words meaning my/our that precede a kin term (both scripts)")
    possessive_listener: list[str] = Field(description="words meaning your that precede a kin term (both scripts)")
    respectful_markers: list[str] = Field(description="verb/pronoun endings or particles that mark respect for the referent, as regex-safe literal strings; [] if none")
    informal_markers: list[str] = Field(description="endings/particles that mark familiarity (used for one's own children); [] if none")
    generic_heads: list[str] = Field(description="nouns that precede a kin term used as polite address to non-relatives (shop, driver, neighbour, teacher)")
    frozen: list[str] = Field(description="high-frequency words whose endings must never be stripped (today, yesterday, very)")
    terms: list[TermOut]


@dataclass
class LanguageTable:
    code: str
    name: str
    native_name: str
    script: str               # regex for the heritage script block, "" for Latin
    locale: str
    final_strip: list[str]
    suffixes: list[str]
    roman_suffixes: list[str]
    possessive_speaker: list[str]
    possessive_listener: list[str]
    respectful_markers: list[str]
    informal_markers: list[str]
    generic_heads: list[str]
    frozen: list[str]
    terms: list[KinTermDef]
    verified: bool
    source: str
    notes: str = ""
    dropped: list[str] = field(default_factory=list)  # terms/patterns rejected by validation

    @property
    def script_re(self) -> re.Pattern | None:
        return re.compile(self.script) if self.script else None

    def is_script(self, s: str) -> bool:
        return bool(self.script_re and self.script_re.search(s))

    def surface_forms(self) -> dict[str, KinTermDef]:
        idx: dict[str, KinTermDef] = {}
        for d in self.terms:
            for k in (d.term, d.script, *d.variants):
                if k:
                    idx.setdefault(normalize_term(k), d)
        return idx

    def to_json(self) -> dict:
        return {"code": self.code, "name": self.name, "native_name": self.native_name, "script": self.script, "locale": self.locale,
                "final_strip": self.final_strip, "suffixes": self.suffixes, "roman_suffixes": self.roman_suffixes,
                "possessive_speaker": self.possessive_speaker, "possessive_listener": self.possessive_listener,
                "respectful_markers": self.respectful_markers, "informal_markers": self.informal_markers, "generic_heads": self.generic_heads,
                "frozen": self.frozen, "verified": self.verified, "source": self.source, "notes": self.notes,
                "terms": [{"term": d.term, "script": d.script, "variants": list(d.variants), "patterns": list(d.patterns), "gloss": d.gloss, "kind": d.kind, "notes": d.notes} for d in self.terms]}


TAMIL_META = dict(final_strip=["ம்", "்"],
                  suffixes=["லேர்ந்து", "லிருந்து", "க்கிட்ட", "கிட்ட", "வோட", "யோட", "ஓட", "ோட", "க்காக", "க்கு", "ுக்கு", "க்கும்", "யும்", "வும்", "உம்", "ும்", "யில", "யிலே", "ல", "ில", "ிலே", "ாவை", "யை", "வை", "ை", "ன்னு", "ஆ", "ா", "ே"],
                  roman_suffixes=["lerndhu", "lirundhu", "kitta", "kkitta", "voda", "yoda", "oda", "kkaaga", "ukku", "kku", "kkum", "ukkum", "yum", "vum", "um", "yila", "ila", "la", "le", "vai", "yai", "ai", "nnu", "aa", "a", "va", "vaa", "ya", "yaa", "ku", "laam"],
                  possessive_speaker=["என்", "எங்க", "en", "enga", "ennoda", "என்னோட"], possessive_listener=["உன்", "உங்க", "un", "unga", "unnoda", "உன்னோட", "ungaloda"],
                  respectful_markers=["ாரு", "ாரா", "ாங்க", "ீங்க", "ாரே", "aaru", "aaraa", "aanga", "eenga", "aare"], informal_markers=["ான்", "ாள்", "ானா", "ாளா", "aan", "aal", "aanaa"],
                  generic_heads=["கடை", "கடைக்காரர்", "கடைக்காரி", "டிரைவர்", "ஆட்டோ", "பக்கத்து", "வீட்டு", "பூக்காரி", "பால்காரன்", "ஸ்கூல்", "ஆபீஸ்", "kadai", "driver", "auto", "pakkathu", "veettu", "shop", "school", "office"],
                  frozen=["இன்னைக்கு", "நாளைக்கு", "நேத்து", "எப்போ", "இப்போ", "அப்போ", "ரொம்ப", "நல்லா", "கொஞ்சம்", "innaikku", "naalaikku", "nethu", "eppo", "ippo", "romba", "nallaa"])


def _validate_terms(code: str, raw: list[dict]) -> tuple[list[KinTermDef], list[str]]:
    out, dropped = [], []
    seen: set[str] = set()
    for r in raw:
        term = (r.get("term") or "").strip().lower()
        if not term or term in seen:
            continue
        pats = []
        for p in r.get("patterns", []) or []:
            p = p.strip().lower().replace(" ", "")
            if p and all(s in STEP_WORDS for s in p.split(".")) and len(p.split(".")) <= 4:
                pats.append(p)
            elif p:
                dropped.append(f"{term}: pattern {p!r}")
        kind = r.get("kind") if r.get("kind") in ("kin", "endearment", "honorific") else "kin"
        if kind == "kin" and not pats:
            dropped.append(f"{term}: no valid pattern"); continue
        if kind != "kin":
            pats = []
        seen.add(term)
        out.append(KinTermDef(term, (r.get("script") or term).strip(), tuple(pats), (r.get("gloss") or "").strip() or term, kind,
                              tuple(v.strip() for v in (r.get("variants") or []) if v and v.strip()), (r.get("notes") or "").strip()))
    return out, dropped


def _tamil() -> LanguageTable:
    return LanguageTable("ta", "Tamil", NATIVE["ta"], SCRIPT["ta"], LOCALE["ta"], **TAMIL_META, terms=list(KIN_TERMS), verified=True, source="hand",
                         notes="Hand-written gold table (app/graph/ontology.py).")


@lru_cache(maxsize=32)
def load_table(code: str) -> LanguageTable:
    if code == "ta":
        return _tamil()
    if code not in MUSE_LANGUAGES:
        raise KeyError(f"unsupported language {code!r}; Muse Voice Transcribe languages: {sorted(MUSE_LANGUAGES)}")
    path = DIR / f"{code}.json"
    if not path.exists():
        raise FileNotFoundError(f"no kin table for {code}; run scripts/make_kin_tables.py")
    j = json.loads(path.read_text(encoding="utf-8"))
    terms, dropped = _validate_terms(code, j.get("terms", []))
    if dropped:
        log.info("%s: dropped %d invalid entries", code, len(dropped))
    return LanguageTable(code, MUSE_LANGUAGES[code], NATIVE[code], SCRIPT.get(code, ""), LOCALE[code],
                         final_strip=j.get("final_strip", []), suffixes=sorted(j.get("suffixes", []), key=len, reverse=True), roman_suffixes=j.get("roman_suffixes", []),
                         possessive_speaker=[w.lower() for w in j.get("possessive_speaker", [])], possessive_listener=[w.lower() for w in j.get("possessive_listener", [])],
                         respectful_markers=j.get("respectful_markers", []), informal_markers=j.get("informal_markers", []),
                         generic_heads=[w.lower() for w in j.get("generic_heads", [])], frozen=j.get("frozen", []), terms=terms,
                         verified=bool(j.get("verified", False)), source=j.get("source", "muse-spark-1.3"), notes=j.get("notes", ""), dropped=dropped)


def all_codes() -> list[str]:
    return sorted(MUSE_LANGUAGES)


def available_codes() -> list[str]:
    return [c for c in all_codes() if c == "ta" or (DIR / f"{c}.json").exists()]

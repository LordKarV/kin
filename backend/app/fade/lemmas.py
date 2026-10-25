"""Light heritage-language lemmatizer for Fade. Tamil is agglutinative: strip the common case/clitic suffixes so
"மதுரைக்கு", "மதுரையில", "மதுரை" share one mastery row. Deliberately shallow; good enough to track vocabulary."""
from __future__ import annotations

import re
import unicodedata

TAMIL = re.compile(r"[஀-௿]")
VIRAMA = "்"
# longest first; applied once (one layer) to avoid over-stripping
TAMIL_SUFFIXES = ["லேர்ந்து", "லிருந்து", "க்கிட்ட", "கிட்ட", "வோட", "யோட", "ஓட", "ோட", "க்காக", "க்கு", "ுக்கு", "க்கும்", "யும்", "வும்", "உம்", "ும்",
                  "யில", "யிலே", "ல", "ில", "ிலே", "ாவை", "யை", "வை", "ை", "ன்னு", "ஆ", "ா", "ே"]
ROMAN_SUFFIXES = ["lerndhu", "lirundhu", "kitta", "voda", "yoda", "oda", "kkaaga", "ukku", "kku", "yum", "vum", "um", "yila", "ila", "la", "vai", "yai", "ai", "nnu", "aa"]
FROZEN = {"இன்னைக்கு", "நாளைக்கு", "நேத்து", "எப்போ", "இப்போ", "அப்போ", "ரொம்ப", "நல்லா", "கொஞ்சம்", "innaikku", "naalaikku", "nethu", "eppo", "ippo", "romba", "nallaa"}
STOP = {"நான்", "நீ", "அது", "இது", "ஒரு", "தான்", "இல்ல", "உன்", "என்", "உங்க", "எங்க", "naan", "nee", "adhu", "idhu", "oru", "thaan", "illa", "un", "en", "unga", "enga"}


def _clean(tok: str) -> str:
    tok = unicodedata.normalize("NFC", tok).strip("\"'“”‘’()[]{},;:!?।.")
    return tok


ENGLISH_STOP = {"the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "to", "of", "in", "on", "at", "for", "with", "you", "your", "i", "my",
                "we", "our", "he", "she", "it", "they", "this", "that", "ok", "okay", "yes", "no", "not", "phone", "call", "video"}


def _table(lang: str):
    from ..graph.kin_tables import load_table
    try:
        return load_table(lang)
    except (KeyError, FileNotFoundError):
        return load_table("ta")


def lemma(tok: str, lang: str = "ta") -> str:
    t = _clean(tok)
    tb = _table(lang)
    frozen = set(tb.frozen) | (FROZEN if lang == "ta" else set())
    if t in frozen or t.lower() in frozen:
        return t if tb.is_script(t) else t.lower()
    if tb.is_script(t):
        for suf in (tb.suffixes or []):
            if t.endswith(suf) and len(t) - len(suf) >= 2:
                return t[: -len(suf)]
        return t
    if "-" in t:
        return t.lower().split("-")[0]
    t = t.lower()
    for suf in sorted(set(tb.roman_suffixes) | (set(ROMAN_SUFFIXES) if lang == "ta" else set()), key=len, reverse=True):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: -len(suf)]
    return t


def _lemma_tamil_legacy(tok: str) -> str:
    t = _clean(tok)
    if TAMIL.search(t):
        for suf in TAMIL_SUFFIXES:
            if t.endswith(suf) and len(t) - len(suf) >= 2:
                base = t[: -len(suf)]
                # restore a dropped pulli when the stem ended in a consonant + case vowel sign (ரவியும் → ரவி stays; மதுரைக்கு → மதுரை)
                return base
        return t
    if "-" in t:  # "Madurai-kku": the suffix is already split off
        return t.lower().split("-")[0]
    t = t.lower()
    for suf in ROMAN_SUFFIXES:
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: -len(suf)]
    return t


def is_heritage(tok: str, lang: str = "ta") -> bool:
    t = _clean(tok)
    tb = _table(lang)
    if tb.is_script(t):
        return True
    if tb.script:  # a non-Latin-script language: Latin tokens are romanization only if they look like it (Tamil-style clusters)
        return bool(re.search(r"(aa|zh|nn|tt|dh|th|kk|ng|nga|ch)", t.lower())) and t.isalpha() and len(t) >= 4
    # Latin-script heritage language (Spanish, Tagalog...): the grandparent side speaks it; anything that is not an obvious English word counts
    return t.isalpha() and len(t) >= 3 and t.lower() not in ENGLISH_STOP


def heritage_lemmas(text: str, lang: str = "ta") -> list[str]:
    out: list[str] = []
    for tok in re.findall(r"\S+", text):
        t = _clean(tok)
        if len(t) < 2 or not is_heritage(t, lang):
            continue
        lm = lemma(t, lang)
        if lm in STOP or len(lm) < 2:
            continue
        if lm not in out:
            out.append(lm)
    return out

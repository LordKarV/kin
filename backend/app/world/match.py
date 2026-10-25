"""Cross-script alias matching over live transcripts. Pure, stdlib only.

One char trie over fold(form) plus a skeleton trie for Latin forms, scanned from every position of the folded text.
Works without word segmentation (scripts written without spaces) and on partial transcripts. Offsets in every Hit
point into the ORIGINAL text, so a caller can underline exactly what was said.
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

log = logging.getLogger(__name__)

ISOLATING = {"han", "hiragana", "katakana", "thai", "lao", "khmer", "myanmar"}
_SINGLE_CHAR_CUED = {"han", "hiragana", "katakana"}   # single-char forms in the other isolating scripts are never accepted
_ABUGIDA = {"thai", "lao", "khmer", "myanmar"}
_FOLLOWING_VOWELS = set("ะาๅະາ")   # spacing (Lo) vowels written after their consonant; SARA AM folds to Mn + SARA AA
# Kinds whose capitalized Latin forms are names, so a lowercase match in cased text is the common word (will, may).
# Things, groups and concept keys are common nouns that STT writes lowercase, so they stay case-blind.
_CASED_KINDS = {"person"}
CUE_BEFORE = set("和跟与同叫给找带问对是让") | {"と"}
CUE_AFTER = set("说她他也都的呢吗们") | {"さん", "ちゃん", "くん", "君", "と", "が", "は", "も"}
# Last chars of common time words, connectives and verbs: a single-ideograph name right after one is a new word.
# Known limit: a longer word that starts with one of these chars still gives its next char; a word breaker is the upgrade.
_WORD_END = set("了天后以就还又才但说见")
_LEADING_VOWELS = set("เแโใไເແໂໃໄ")   # vowels written before their consonant
_SCRIPT_ALIASES = {"cjk": "han", "ideographic": "han"}
_END = None   # trie terminal key; real keys are single characters
_STRIP = ""   # terminal of a form with its final virama dropped; valid only before a case suffix


@lru_cache(maxsize=4096)
def script_of(ch: str) -> str:
    """First word of the Unicode name ("LATIN SMALL LETTER A" -> "latin"); CJK ideographs -> "han"."""
    name = unicodedata.name(ch, "")
    if not name:
        return "common"
    words = name.split(" ")
    if words[0] in ("FULLWIDTH", "HALFWIDTH") and len(words) > 1:
        words = words[1:]
    first = words[0].split("-", 1)[0].lower()
    return _SCRIPT_ALIASES.get(first, first)


def _is_letter(ch: str) -> bool:
    return unicodedata.category(ch)[0] in "LM"


@lru_cache(maxsize=8192)
def _fold_char(c: str, after_latin: bool) -> str:
    cat = unicodedata.category(c)
    if cat[0] in "PSZ":
        return " "
    if cat == "Mn" and after_latin:
        return ""                       # a decomposed accent on a Latin letter
    k = unicodedata.normalize("NFKC", c)
    if k and script_of(k[0]) == "latin":
        return "".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x)).casefold()
    return k.casefold()


def fold(s: str) -> tuple[str, list[int]]:
    """Per char. Latin: NFKD, drop combining marks, casefold (accents and case dropped). Other scripts: NFKC + casefold, vowel
    signs KEPT. Unicode P/S/Z -> ' '. Returns the folded string and, for each folded char, the index of the original
    char it came from (span offsets survive NFKC expansion)."""
    out: list[str] = []
    idx: list[int] = []
    after_latin = False
    for i, c in enumerate(s):
        f = _fold_char(c, after_latin)
        out.append(f)
        idx.extend([i] * len(f))
        if unicodedata.category(c) != "Mn":
            after_latin = script_of(c) == "latin"
    return "".join(out), idx


def _skel_mapped(folded: str) -> tuple[str, list[int], list[int]]:
    """Skeleton of an already folded string plus, per skeleton char, its [start, end) in the folded string."""
    out: list[str] = []
    st: list[int] = []
    en: list[int] = []
    i, n = 0, len(folded)
    while i < n:
        if folded.startswith("ph", i):
            c, w = "f", 2
        else:
            c, w = ("i" if folded[i] == "y" else folded[i]), 1
        if out and out[-1] == c and "a" <= c <= "z":
            en[-1] = i + w                  # collapse doubled letters (Lynn -> lin)
        else:
            out.append(c)
            st.append(i)
            en.append(i + w)
        i += w
    return "".join(out), st, en


def skel(latin: str) -> str:
    """Latin phonetic skeleton: y->i, ph->f, collapse doubled letters (Lynn -> lin). Linh stays linh."""
    return _skel_mapped(fold(latin)[0])[0]


@dataclass(frozen=True)
class Hit:
    start: int              # offsets into the ORIGINAL text
    end: int
    surface: str
    kind: str
    ids: tuple[int, ...]
    form: str
    exact: bool


@lru_cache(maxsize=64)
def _suffixes(speaker_lang: str) -> frozenset[str]:
    if not speaker_lang:
        return frozenset()
    from ..graph.kin_tables import load_table   # lazy: kin_tables pulls pydantic; the matcher itself stays stdlib
    try:
        t = load_table(speaker_lang)
    except (KeyError, FileNotFoundError) as e:
        log.info("no suffixes for speaker_lang %r: %s", speaker_lang, e)
        return frozenset()
    raw = list(t.suffixes) + (list(t.roman_suffixes) if t.script else [])   # roman suffixes only for non-Latin tables
    folded = (fold(x)[0].strip() for x in raw)
    return frozenset(x for x in folded if x and " " not in x)


def _form_script(folded_form: str) -> str:
    return next((script_of(c) for c in folded_form if _is_letter(c)), "common")


class AliasIndex:
    # Known limit: pure-Python dict trie, about 1 ms per 300-char line at 5k forms; switch to pyahocorasick past ~50k forms.
    def __init__(self, forms: Iterable[tuple[str, str, int]]):
        self._exact: dict = {}
        self._skel: dict = {}
        for form, kind, id_ in forms:
            f = fold(form)[0].strip()
            if not f:
                continue
            script = _form_script(f)
            self._insert(self._exact, f, form, kind, id_, script)
            if script != "latin" and len(f) > 1 and unicodedata.name(f[-1], "").endswith(" VIRAMA"):
                # a final virama drops when a case suffix attaches, so also index the form without it.
                self._insert(self._exact, f[:-1], form, kind, id_, script, _STRIP)
            if script == "latin":
                self._insert(self._skel, _skel_mapped(f)[0], form, kind, id_, script)

    @staticmethod
    def _insert(trie: dict, key: str, form: str, kind: str, id_: int, script: str, end=_END) -> None:
        node = trie
        for ch in key:
            node = node.setdefault(ch, {})
        term = node.setdefault(end, {"len": len(key), "script": script, "kinds": {}, "needs_suffix": end == _STRIP})
        entry = term["kinds"].setdefault(kind, [form, [], set()])   # [shown form, ids, ids with a non-capitalized form]
        if id_ not in entry[1]:
            entry[1].append(id_)
        if not form[:1].isupper():
            entry[2].add(id_)

    @staticmethod
    def _walk(trie: dict, s: str, i: int) -> list[tuple[int, dict]]:
        """Every terminal reachable from position i, as (end, terminal), longest first."""
        out = []
        node = trie
        for j in range(i, len(s)):
            node = node.get(s[j])
            if node is None:
                break
            for end in (_STRIP, _END):     # reversed below, so the plain terminal is tried first
                if end in node:
                    out.append((j + 1, node[end]))
        out.reverse()
        return out

    def scan(self, text: str, speaker_lang: str = "") -> list[Hit]:
        folded, idx = fold(text)
        if not folded:
            return []
        sufs = _suffixes(speaker_lang)
        cands: list[tuple[int, int, dict, bool]] = []   # (folded start, folded end, terminal, exact)
        for i in range(len(folded)):
            found = self._walk(self._exact, folded, i)
            pick = self._first_ok(folded, i, found, sufs)
            if pick:
                cands.append((i, pick[0], pick[1], True))
        sk, st, en = _skel_mapped(folded)
        for a in range(len(sk)):
            found = [(en[b - 1], t) for b, t in self._walk(self._skel, sk, a)]
            pick = self._first_ok(folded, st[a], found, sufs)
            if pick:
                cands.append((st[a], pick[0], pick[1], False))
        return self._suppress(cands, text, idx)

    def _first_ok(self, s: str, i: int, found: list[tuple[int, dict]], sufs: frozenset[str]):
        for j, term in found:
            if self._boundary_ok(s, i, j, term, sufs, longer=len(found) > 1):
                return j, term
        return None

    @staticmethod
    def _boundary_ok(s: str, i: int, j: int, term: dict, sufs: frozenset[str], longer: bool) -> bool:
        script = term["script"]
        if script in ISOLATING:
            if term["len"] >= 2:
                return _isolating_ok(s, i, j, script)
            if script not in _SINGLE_CHAR_CUED or longer:
                return False
            left = s[i - 1] if i > 0 else ""
            right = s[j:]
            if left in CUE_BEFORE:
                return True
            # A same-script letter on the left is the same word even with a cue on the right, unless it ends a
            # common word (_WORD_END); a letter of another script or punctuation on the left is a boundary.
            # Deliberately strict: with no cue BOTH sides must be boundaries, else a longer
            # word at text start that begins with the name gives the name. Cost: any other same-script char before
            # the name and a name at text start with no cue after it give nothing (pinned in test_match.py).
            left_ok = not left or left in _WORD_END or _other_script(left, script)
            return left_ok and (any(right.startswith(c) for c in CUE_AFTER) or _cjk_edge(right[:1]))
        if term["needs_suffix"]:
            return _left_ok(s, i, script) and _rest_of_token(s, j) in sufs
        return _left_ok(s, i, script) and _right_ok(s, j, script, sufs)

    @staticmethod
    def _suppress(cands, text: str, idx: list[int]) -> list[Hit]:
        """Longest original span first, exact before skeleton; overlapping spans dropped. One hit per (kind, id) per span:
        a skeleton candidate on the same span as an exact one adds a second Hit(exact=False) with only the new ids, so
        3.4 ranking sees Lynn as an alternative for "Lin" and can still give exact ids their +0.5."""
        spans = []
        for fi, fj, term, exact in cands:
            # end at the next folded char's source, so dropped trailing accents (NFD "José") stay inside the span
            e = max(idx[fj - 1] + 1, idx[fj]) if fj < len(idx) else len(text)
            spans.append((idx[fi], e, term, exact))
        spans.sort(key=lambda c: (-(c[1] - c[0]), not c[3], c[0]))
        # Case is a signal only when the transcript has any capital, so all-lowercase STT and romanized heritage text still match.
        # Known limit: a sentence-initial "Will you" still matches, and a lowercase kin word ("my <kin term>") in cased
        # text is lost unless that person also has a lowercase form; a POS tagger is the upgrade.
        cased = any(c.isupper() for c in text)
        taken = [False] * len(text)
        accepted: set[tuple[int, int]] = set()
        emitted: set[tuple[int, int, str, int]] = set()
        out: list[Hit] = []
        for s, e, term, exact in spans:
            common_word = cased and text[s].islower()
            # per id, not per terminal: Mom (id 1) and mom (id 2) share one terminal, and only id 2 is case-blind
            kinds = [(k, (form, [i for i in ids if i in lower] if common_word and k in _CASED_KINDS else ids))
                     for k, (form, ids, lower) in term["kinds"].items()]
            kinds = [(k, v) for k, v in kinds if v[1]]
            if not kinds:
                continue                    # leave the span free for another candidate
            if (s, e) not in accepted:
                if any(taken[s:e]):
                    continue
                accepted.add((s, e))
                for k in range(s, e):
                    taken[k] = True
            for kind, (form, ids) in kinds:
                new = tuple(i for i in ids if (s, e, kind, i) not in emitted)
                if new:
                    emitted.update((s, e, kind, i) for i in new)
                    out.append(Hit(s, e, text[s:e], kind, new, form, exact))
        out.sort(key=lambda h: (h.start, h.kind, not h.exact))
        return out


def _isolating_ok(s: str, i: int, j: int, script: str) -> bool:
    """2+ char isolating forms need no boundary, except where the text plainly continues the same word."""
    if script == "katakana":
        # a run of this script is one word; particles and honorifics are written in another script
        return not (i > 0 and script_of(s[i - 1]) == "katakana") and not (j < len(s) and script_of(s[j]) == "katakana")
    if script in _ABUGIDA:
        # a leading vowel before the match belongs to its first consonant, a vowel sign or tone mark after it to
        # its last: neither is the name.
        # Known limit: no syllable segmentation, so a longer word or a consonant cluster that contains the name still
        # gives it; a word breaker for the script is the upgrade.
        if i > 0 and s[i - 1] in _LEADING_VOWELS:
            return False
        return j == len(s) or (unicodedata.category(s[j]) not in ("Mn", "Mc") and s[j] not in _FOLLOWING_VOWELS)
    return True


def _cjk_edge(ch: str) -> bool:
    """Start/end of text, space, punctuation (all folded to ' ') or a Latin letter."""
    return not ch or not _is_letter(ch) or script_of(ch) == "latin"


def _other_script(ch: str, script: str) -> bool:
    # A letter of another script is a boundary too: a Latin name inside code-mixed text must still match.
    return not _is_letter(ch) or (unicodedata.category(ch)[0] == "L" and script_of(ch) != script)


def _left_ok(s: str, i: int, script: str) -> bool:
    return i == 0 or _other_script(s[i - 1], script)


def _right_ok(s: str, j: int, script: str, sufs: frozenset[str]) -> bool:
    if j == len(s) or _other_script(s[j], script):
        return True
    return _rest_of_token(s, j) in sufs


def _rest_of_token(s: str, j: int) -> str:
    k = j
    while k < len(s) and _is_letter(s[k]):
        k += 1
    return s[j:k]

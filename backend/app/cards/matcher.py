"""Fast lexicon matcher over one transcript line (partials included), target < 5 ms on a 30-word line.

Whole-word, longest-form-first, nested spans suppressed. Native scripts keep their combining marks (tokens are split on
whitespace only and normalized with ontology.normalize_term, which keeps vowel signs in every script). Inflection: the
LAST token of a form may carry one case suffix from the language's kin table (பொங்கலுக்கு, pongalukku), only for forms of
4+ characters. Fuzzy matching (rapidfuzz) is used only for sayings/long phrases, with a high cutoff; short phrases are
exact only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from ..graph.ontology import normalize_term
from .lexicon import LexEntry

PUNCT = "\"'“”‘’()[]{},;:!?।॥.、。，…"
FUZZY_CUTOFF = 90          # rapidfuzz partial_ratio, 0-100
FUZZY_MIN_TOKENS = 3       # a phrase needs 3+ words and 12+ chars to be fuzzy-matched
FUZZY_MIN_CHARS = 12
FUZZY_SHARED_TOKENS = 2    # prefilter: a saying is fuzzy-scored only if 2+ of its words appear exactly in the line
FUZZY_COMMON_TOKEN = 50    # words in more phrases than this ("is", "the", "hai") are ignored by the prefilter
STEM_MIN_CHARS = 4         # shorter forms never take a suffix ("pal" must not match "palam")


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    source: str
    entry: LexEntry
    method: str            # exact | suffix | fuzzy


@dataclass(frozen=True)
class _Tok:
    start: int
    end: int
    norm: str


def tokenize(text: str) -> list[_Tok]:
    out = []
    for mt in re.finditer(r"\S+", text):
        raw = mt.group(0)
        core = raw.strip(PUNCT)
        if not core:
            continue
        off = mt.start() + raw.find(core)
        n = normalize_term(core)
        if n:
            out.append(_Tok(off, off + len(core), n))
    return out


class Matcher:
    def __init__(self, entries: list[LexEntry], suffixes: tuple[str, ...] = (), final_strip: tuple[str, ...] = ()):
        self.suffixes = tuple(sorted({s for s in (normalize_term(x) for x in suffixes) if s}, key=len, reverse=True))
        self.final_strip = tuple(f for f in final_strip if f)
        self.index: dict[str, list[tuple[tuple[str, ...], LexEntry]]] = {}
        self.phrases: list[tuple[str, int, LexEntry]] = []   # (normalized phrase, n tokens, entry) eligible for fuzzy
        seen: set[tuple[str, ...]] = set()
        for e in entries:
            for f in e.forms:
                toks = tuple(normalize_term(f).split())
                if not toks or toks in seen:
                    continue
                seen.add(toks)
                self.index.setdefault(toks[0], []).append((toks, e))
                joined = " ".join(toks)
                if (e.category == "saying" or len(toks) >= 4) and len(toks) >= FUZZY_MIN_TOKENS and len(joined) >= FUZZY_MIN_CHARS:
                    self.phrases.append((joined, len(toks), e))
        for lst in self.index.values():
            lst.sort(key=lambda te: -len(te[0]))
        by_tok: dict[str, list[int]] = {}
        for k, (phrase, _n, _e) in enumerate(self.phrases):
            for w in set(phrase.split()):
                by_tok.setdefault(w, []).append(k)
        self.phrase_by_tok = {w: ks for w, ks in by_tok.items() if len(ks) <= FUZZY_COMMON_TOKEN}

    # -- token comparison --------------------------------------------------
    def _bases(self, tok: str) -> list[str]:
        """The token with one known suffix removed (and the droppable final restored: பொங்கலுக்கு → பொங்கல்)."""
        out = []
        for s in self.suffixes:
            if tok.endswith(s) and len(tok) - len(s) >= STEM_MIN_CHARS - 1:
                b = tok[: -len(s)]
                out.append(b)
                out += [b + f for f in self.final_strip]
        return out

    def _last_ok(self, tok: str, form_tok: str) -> str | None:
        if tok == form_tok:
            return "exact"
        if len(form_tok) >= STEM_MIN_CHARS and self.suffixes and form_tok in self._bases(tok):
            return "suffix"
        return None

    # -- public --------------------------------------------------------------
    def match(self, text: str) -> list[Match]:
        toks = tokenize(text)
        if not toks:
            return []
        cands: list[tuple[int, int, LexEntry, str]] = []
        for i, t in enumerate(toks):
            for form, e in self.index.get(t.norm, ()):
                n = len(form)
                if i + n > len(toks):
                    continue
                if n == 1:
                    cands.append((i, i, e, "exact"))
                    continue
                if all(toks[i + k].norm == form[k] for k in range(1, n - 1)):
                    how = self._last_ok(toks[i + n - 1].norm, form[-1])
                    if how:
                        cands.append((i, i + n - 1, e, how))
            if self.suffixes and len(t.norm) >= STEM_MIN_CHARS:
                for b in self._bases(t.norm):
                    for form, e in self.index.get(b, ()):
                        if len(form) == 1 and len(form[0]) >= STEM_MIN_CHARS:
                            cands.append((i, i, e, "suffix"))
        if self.phrases and len(toks) >= FUZZY_MIN_TOKENS:
            cands += self._fuzzy(toks, {c[2].key for c in cands})
        return self._suppress(cands, toks, text)

    def _fuzzy(self, toks: list[_Tok], have: set[str]) -> list[tuple[int, int, LexEntry, str]]:
        joined, starts = "", []
        for t in toks:
            starts.append(len(joined))
            joined += t.norm + " "
        joined = joined.rstrip()
        shared: dict[int, int] = {}
        for w in {t.norm for t in toks}:
            for k in self.phrase_by_tok.get(w, ()):
                shared[k] = shared.get(k, 0) + 1
        out = []
        for k in sorted(k for k, c in shared.items() if c >= FUZZY_SHARED_TOKENS):
            phrase, n, e = self.phrases[k]
            if e.key in have or len(toks) < n or len(joined) < 0.9 * len(phrase):
                continue  # a partial shorter than the saying must not "match" half of it
            al = fuzz.partial_ratio_alignment(phrase, joined, score_cutoff=FUZZY_CUTOFF)
            if al is None:
                continue
            i = max(k for k, s in enumerate(starts) if s <= al.dest_start)
            j = max(k for k, s in enumerate(starts) if s < max(al.dest_end, al.dest_start + 1))
            if j - i + 1 >= max(2, n - 1):
                out.append((i, j, e, "fuzzy"))
                have.add(e.key)
        return out

    @staticmethod
    def _suppress(cands, toks: list[_Tok], text: str) -> list[Match]:
        """Longest span first; a span overlapping an already-taken one is dropped (nested-span suppression)."""
        cands.sort(key=lambda c: (-(c[1] - c[0]), -(toks[c[1]].end - toks[c[0]].start), c[3] != "exact", c[0]))
        taken: set[int] = set()
        keys: set[str] = set()
        out = []
        for i, j, e, how in cands:
            if any(k in taken for k in range(i, j + 1)) or e.key in keys:
                continue
            taken.update(range(i, j + 1))
            keys.add(e.key)
            s, en = toks[i].start, toks[j].end
            out.append(Match(s, en, text[s:en], e, how))
        out.sort(key=lambda mm: mm.start)
        return out

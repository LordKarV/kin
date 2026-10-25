"""Entity linker: ASR text (native script and/or romanized) → spans resolved to family-graph nodes.

Pipeline: tokenize → n-gram alias / kin-term matches (longest first, suffix-tolerant) → compositional kin chains
("mother's younger brother", "uncle's son") → name disambiguation (adjacent kin term, co-mentions, place/topic cues,
context salience, speaker proximity, honorific verb endings) → listener-relative rendering.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .kin_tables import LanguageTable, load_table
from .kinship import FamilyGraph
from .ontology import KinTermDef, normalize_term

NON_LATIN = re.compile(r"[^\x00-\x7f]")
GENERIC_HEADS_EN = {"shop", "driver", "auto", "school", "office", "neighbour", "neighbor", "teacher", "doctor", "nurse"}
SIBLING_TERMS = {"anna", "akka", "thambi", "thangai", "mama", "mami"}
COMPOSITIONAL_ONLY = {"paiyan", "ponnu"}
# romanized suffixes common across the Indic languages; each language table adds its own (ROMAN_SUFFIXES ∪ table.roman_suffixes)
ROMAN_SUFFIXES = {"kku", "ukku", "la", "le", "um", "ai", "a", "aa", "ku", "ka", "ki", "ko", "ne", "se", "me", "ya", "s", "es"}


@dataclass
class Span:
    start: int
    end: int
    source: str
    node: str | None            # slug, None if unresolved/generic
    type: str                   # person | dish | place | event | kin
    confidence: float
    method: str
    display: str = ""
    candidates: list[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "source": self.source, "node_id": self.node, "type": self.type,
                "confidence": round(self.confidence, 2), "rendered": self.display, "candidates": self.candidates, "method": self.method}


@dataclass
class _Tok:
    text: str
    start: int
    end: int
    core: str           # punctuation-trimmed
    norm: str           # alias matching: lowercase, dots removed, hyphen suffix dropped (NO vowel collapsing: a doubled vowel can make a different word)
    knorm: str = ""     # kin-term matching: ontology normalization (doubled vowels collapse)


@dataclass
class _Match:
    i: int              # first token index
    j: int              # last token index (inclusive)
    kind: str           # person | thing | kin
    persons: set[int] = field(default_factory=set)
    things: list = field(default_factory=list)
    term: KinTermDef | None = None
    exact: bool = False
    method: str = ""
    bound: bool = False   # kin term bound to a possessive head that has no such relative ("mother's elder sister" when she has none): never resolve from the listener


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower().replace(".", "")
    s = s.strip("\"'“”‘’()[]{},;:!?।-–—、。，")
    s = re.sub(r"-.*$", "", s) if NON_LATIN.search(s) is None and "-" in s else s  # romanized "name-suffix" → name
    return s


def _knorm(s: str) -> str:
    return normalize_term(_norm(s))


def _stem(alias_norm: str, final_strip=("ம்", "்")) -> str:
    """Drop a droppable final (e.g. a final virama, or a final consonant with its virama) so suffixed forms prefix-match."""
    for f in sorted(final_strip, key=len, reverse=True):
        if f and alias_norm.endswith(f):
            return alias_norm[: -len(f)]
    return alias_norm


def _prefix_match(tok_norm: str, alias_norm: str, exact_only: bool = False, table: LanguageTable | None = None) -> bool:
    if not tok_norm or not alias_norm:
        return False
    if tok_norm == alias_norm:
        return True
    if exact_only:
        return False
    if NON_LATIN.search(alias_norm):
        if table is not None and not table.final_strip and not table.suffixes:
            return False  # scripts written without spaces between words: no inflection, exact only
        return tok_norm.startswith(_stem(alias_norm, table.final_strip if table else ("ம்", "்")))
    sufs = ROMAN_SUFFIXES | set(table.roman_suffixes if table else [])
    if tok_norm.startswith(alias_norm) and tok_norm[len(alias_norm):] in sufs:
        return True
    # fuzzy only for long aliases, same initial, strict ratio (spelling variants like lakshmi/lakshmy), never short words
    return len(alias_norm) >= 6 and tok_norm[0] == alias_norm[0] and fuzz.ratio(tok_norm, alias_norm) >= 90


class Linker:
    def __init__(self, graph: FamilyGraph, lang: str | None = None):
        """lang: the speaker's language table (world calls); default the family heritage language, as before."""
        self.g = graph
        try:
            self.table = load_table(lang or graph.heritage_lang)
        except (KeyError, FileNotFoundError):
            self.table = load_table("ta")
        t = self.table
        self.possessive_speaker = set(t.possessive_speaker)
        self.possessive_listener = set(t.possessive_listener)
        self.respectful = re.compile("(" + "|".join(re.escape(x) for x in t.respectful_markers) + r")\b") if t.respectful_markers else None
        self.informal = re.compile("(" + "|".join(re.escape(x) for x in t.informal_markers) + r")\b") if t.informal_markers else None
        self.generic_heads = GENERIC_HEADS_EN | set(t.generic_heads)
        # alias index: normalized alias → set of person ids / list of things
        self.person_alias: dict[str, set[int]] = {}
        for pid, p in graph.people.items():
            for alias, _lang, kind in p.aliases:
                self.person_alias.setdefault(_norm(alias), set()).add(pid)
            self.person_alias.setdefault(_norm(p.name), set()).add(pid)
            if p.lang_name:
                self.person_alias.setdefault(_norm(p.lang_name), set()).add(pid)
        self.thing_alias: dict[str, list] = {}
        for t in graph.things:
            for alias in [t.name, t.lang_name, *t.aliases]:
                if alias:
                    self.thing_alias.setdefault(_norm(alias), []).append(t)
        self.kin_forms: dict[str, KinTermDef] = self.table.surface_forms()  # keys are normalize_term()-ed
        self.max_n = 3

    # ---- public --------------------------------------------------------------
    def link(self, text: str, speaker: str, listener: str, context: list[str] | None = None) -> list[Span]:
        sp = self.g.by_slug[speaker].id if speaker in self.g.by_slug else None
        li = self.g.by_slug[listener].id if listener in self.g.by_slug else None
        salience = self._salience(context or [], speaker, listener)
        toks = self._tokenize(text)
        matches = self._scan(toks)
        matches = self._chain(matches, toks, sp, li)
        spans = self._resolve(matches, toks, text, sp, li, salience)
        spans.sort(key=lambda s: s.start)
        return spans

    def keyterms(self) -> list[str]:
        """Latin-script names/dishes/places to bias the ASR (Deepgram keyterm / Muse keywords)."""
        out: list[str] = []
        for p in self.g.people.values():
            out += [a for a in [p.name, *(a for a, _l, _k in p.aliases)] if a and not NON_LATIN.search(a)]
        for t in self.g.things:
            out += [a for a in [t.name, *t.aliases] if a and not NON_LATIN.search(a)]
        seen, uniq = set(), []
        for w in out:
            if w.lower() not in seen:
                seen.add(w.lower()); uniq.append(w)
        return uniq[:100]

    # ---- stages ---------------------------------------------------------------
    def _tokenize(self, text: str) -> list[_Tok]:
        toks = []
        for mt in re.finditer(r"\S+", unicodedata.normalize("NFC", text)):
            raw = mt.group(0)
            core = raw.strip("\"'“”‘’()[]{},;:!?।")
            off = raw.find(core) if core else 0
            toks.append(_Tok(raw, mt.start() + off, mt.start() + off + len(core), core, _norm(core), _knorm(core)))
        return toks

    def _scan(self, toks: list[_Tok]) -> list[_Match]:
        taken = [False] * len(toks)
        found: list[_Match] = []
        for n in range(self.max_n, 0, -1):
            for i in range(0, len(toks) - n + 1):
                if any(taken[i:i + n]):
                    continue
                window = toks[i:i + n]
                mt = self._match_window(window, i)
                if mt:
                    found.append(mt)
                    for k in range(i, i + n):
                        taken[k] = True
        found.sort(key=lambda mm: mm.i)
        return found

    def _match_window(self, window: list[_Tok], i: int) -> _Match | None:
        j = i + len(window) - 1
        norms = [t.norm for t in window]
        knorms = [t.knorm for t in window]

        def hit(alias: str, toks_norm: list[str], exact_only: bool = False) -> bool:
            parts = alias.split(" ")
            if len(parts) != len(toks_norm):
                return False
            return all(a == b for a, b in zip(parts[:-1], toks_norm[:-1])) and _prefix_match(toks_norm[-1], parts[-1], exact_only, self.table)

        # 1) person aliases
        persons: set[int] = set()
        exact = False
        for alias, ids in self.person_alias.items():
            if hit(alias, norms):
                persons |= ids
                exact = exact or (" ".join(norms) == alias)
        # 2) kin terms (endearments/honorifics and very short terms must match exactly: a two-letter term is not the start of a longer name)
        term = None
        term_exact = False
        for surf, d in self.kin_forms.items():
            strict = d.kind != "kin" or len(surf) < 4
            if hit(surf, knorms, exact_only=strict):
                if term is None or len(surf) > len(term.term):
                    term, term_exact = d, (" ".join(knorms) == surf)
        # 3) things
        things = []
        for alias, ts in self.thing_alias.items():
            if hit(alias, norms):
                for t in ts:
                    if t not in things:
                        things.append(t)
        # an exact person alias beats a kin term; an exact kin term beats a fuzzy/prefix person match
        if persons and (exact or len(window) > 1 or not term or not term_exact):
            return _Match(i, j, "person", persons=persons, exact=exact)
        if term:
            return _Match(i, j, "kin", term=term, persons=persons)
        if things:
            return _Match(i, j, "thing", things=things)
        if persons:
            return _Match(i, j, "person", persons=persons, exact=exact)
        return None

    def _chain(self, matches: list[_Match], toks: list[_Tok], sp: int | None, li: int | None) -> list[_Match]:
        """'HEAD kin' sequences: resolve HEAD to a person, then the kin term from that person's perspective.
        Emits two resolved matches (head and referent) so both identities survive, e.g. "Ravi's son Vishnu"
        pins Ravi to the Ravi whose son is Vishnu, and the kin term to Vishnu."""
        out: list[_Match] = []
        k = 0
        while k < len(matches):
            a = matches[k]
            b = matches[k + 1] if k + 1 < len(matches) else None
            if (b and b.kind == "kin" and b.term and b.term.patterns and b.i == a.j + 1 and a.kind in ("person", "kin")
                    and not self._generic_use(b, matches, toks) and not (a.kind == "kin" and self._generic_use(a, matches, toks))):
                heads = self._head_candidates(a, toks, sp, li)
                referents = {h: self.g.resolve_kin_term(b.term, h) for h in heads}
                referents = {h: r for h, r in referents.items() if r}
                if heads and not referents and self._is_possessive_chain(a, b, toks):
                    out.append(a if a.kind == "person" else _Match(a.i, a.j, "person", persons=heads, exact=True, method="chain-head"))
                    out.append(_Match(b.i, b.j, "kin", term=b.term, bound=True))
                    k += 2
                    continue
                if referents:
                    nxt = matches[k + 2] if k + 2 < len(matches) else None
                    head, chosen = None, set()
                    if nxt and nxt.kind == "person" and nxt.i == b.j + 1:
                        for h, r in referents.items():
                            if r & nxt.persons:
                                head, chosen = h, r & nxt.persons
                    if not chosen:
                        if len(referents) == 1:
                            head, chosen = next(iter(referents.items()))
                        else:
                            head = self._pick_person(set(referents), toks, a.i, a.j, sp, li, {}, [])
                            chosen = referents[head]
                    if chosen:
                        out.append(_Match(a.i, a.j, "person", persons={head}, exact=True, method="chain-head"))
                        out.append(_Match(b.i, b.j, "person", persons=chosen, exact=True, method="chain"))
                        k += 2
                        continue
            out.append(a)
            k += 1
        return out

    @staticmethod
    def _is_possessive_chain(a: _Match, b: _Match, toks: list[_Tok]) -> bool:
        """'X-oda/X-vukku KIN' or 'X KIN' where X is a resolved person: the kin term belongs to X."""
        head_tok = toks[a.j].norm
        return head_tok.endswith(("oda", "voda", "yoda", "ஓட", "வோட", "யோட", "kku", "க்கு", "ukku")) or b.i == a.j + 1

    def _head_candidates(self, a: _Match, toks: list[_Tok], sp: int | None, li: int | None) -> set[int]:
        if a.kind == "person":
            return set(a.persons)
        if a.kind == "kin" and a.term:
            return self._kin_candidates(a, toks, sp, li)
        return set()

    def _kin_candidates(self, mm: _Match, toks: list[_Tok], sp: int | None, li: int | None) -> set[int]:
        term = mm.term
        if term is None or not term.patterns:
            return set()
        prev = toks[mm.i - 1].norm if mm.i > 0 else ""
        if prev in self.possessive_speaker and sp is not None:
            return self.g.resolve_kin_term(term, sp)
        if prev in self.possessive_listener and li is not None:
            return self.g.resolve_kin_term(term, li)
        if term.term in COMPOSITIONAL_ONLY:
            return set()
        from_listener = self.g.resolve_kin_term(term, li) if li is not None else set()
        if from_listener:
            return from_listener
        return self.g.resolve_kin_term(term, sp) if sp is not None else set()

    def _resolve(self, matches, toks, text, sp, li, salience) -> list[Span]:
        spans: list[Span] = []
        # first pass: unambiguous persons and things give co-mention context for the ambiguous ones
        prelim: dict[int, int] = {}
        for idx, mm in enumerate(matches):
            if mm.kind == "person" and len(mm.persons) == 1:
                prelim[idx] = next(iter(mm.persons))
            elif mm.kind == "kin":
                c = self._kin_candidates(mm, toks, sp, li)
                if len(c) == 1:
                    prelim[idx] = next(iter(c))
        co_mentions = list(prelim.values())
        place_things = [t for mm in matches if mm.kind == "thing" for t in mm.things if t.kind == "place"]

        for idx, mm in enumerate(matches):
            start, end = toks[mm.i].start, toks[mm.j].end
            source = text[start:end]
            if mm.kind == "thing":
                t = self._pick_thing(mm.things, toks, mm)
                spans.append(Span(start, end, source, t.slug, t.kind, 0.9, "alias", display=t.name, note=t.note))
                continue
            if mm.kind == "kin":
                if mm.bound:
                    continue  # bound to a head with no such relative; leave to the translator
                if self._generic_use(mm, matches, toks):
                    spans.append(Span(start, end, source, None, "kin", 0.3, "generic-address", display=mm.term.gloss if mm.term else ""))
                    continue
                cands = self._kin_candidates(mm, toks, sp, li)
                if not cands:  # a relative KIN has not met yet: the overlay turns this into a "Who is X?" card
                    spans.append(Span(start, end, source, None, "kin", 0.0, "unknown-relative", display=mm.term.gloss if mm.term else ""))
                    continue
                if len(cands) > 1:
                    pid = self._pick_person(cands, toks, mm.i, mm.j, sp, li, salience, co_mentions, place_things, vocative=True)
                    conf = 0.7
                else:
                    pid = next(iter(cands)); conf = 0.9
                spans.append(self._person_span(start, end, source, pid, li, conf, "kin-term", sorted(self.g.people[c].slug for c in cands)))
                continue
            # person name
            cands = set(mm.persons)
            if len(cands) == 1:
                pid = next(iter(cands)); conf = 0.95 if mm.exact else 0.85; method = mm.method or "alias"
            else:
                pid = self._pick_person(cands, toks, mm.i, mm.j, sp, li, salience, co_mentions, place_things)
                conf = 0.75; method = "disambiguated"
            spans.append(self._person_span(start, end, source, pid, li, conf, method, sorted(self.g.people[c].slug for c in cands)))
        return spans

    def _person_span(self, start, end, source, pid, li, conf, method, candidates) -> Span:
        display = self.g.render(li, pid) if li is not None else self.g.people[pid].name
        return Span(start, end, source, self.g.people[pid].slug, "person", conf, method, display=display, candidates=candidates)

    def _pick_thing(self, things, toks, mm):
        if len(things) == 1:
            return things[0]
        last = toks[mm.j].norm
        dative = last.endswith(("க்கு", "kku", "ukku"))
        for t in things:  # dish vs event with the same name: dative/'for X' → event, else event unless a dish qualifier matched
            if t.kind == "event" and (dative or mm.j == mm.i):
                return t
        return things[0]

    def _generic_use(self, mm: _Match, matches: list[_Match], toks: list[_Tok]) -> bool:
        if mm.term is None or mm.term.term not in SIBLING_TERMS or mm.persons:
            return False
        prev = toks[mm.i - 1].norm if mm.i > 0 else ""
        if prev in self.possessive_speaker | self.possessive_listener:
            return False
        prevk = toks[mm.i - 1].knorm if mm.i > 0 else ""
        if any(prev.endswith(_stem(h, self.table.final_strip)) or h in prev or h in prevk for h in self.generic_heads):
            return True
        # two bare sibling terms in a row ("elder brother younger brother") is a generic phrase, not two relatives
        for other in matches:
            if other is not mm and other.kind == "kin" and other.term and other.term.term in SIBLING_TERMS and not other.persons and abs(other.i - mm.j) <= 1:
                return True
        return False

    def _pick_person(self, cands: set[int], toks, i, j, sp, li, salience, co_mentions, place_things=(), vocative=False) -> int:
        scores: dict[int, float] = {c: 0.0 for c in cands}
        sent = " ".join(t.norm for t in toks)
        resp = bool(self.respectful and self.respectful.search(sent)); inf = bool(self.informal and self.informal.search(sent))
        for c in cands:
            node = self.g.people[c]
            if vocative and li is not None and c == li and (i == 0 or toks[j + 1].core.startswith(("நீ", "nee")) if j + 1 < len(toks) else True):
                scores[c] += 3
            for other in co_mentions:
                if other == c:
                    scores[c] += 3
                else:
                    d = self.g.distance(c, other)
                    scores[c] += 2.5 if d == 1 else 1.0 if d == 2 else 0.0
            for t in place_things:
                if any(a.lower() in node.notes.lower() for a in [t.name, *t.aliases] if a and not NON_LATIN.search(a) and len(a) > 3):
                    scores[c] += 2
                if any(a.lower() in t.note.lower() for a, _l, k in node.aliases if k == "address"):
                    scores[c] += 2
            for cue in node.cues:
                cn = _norm(cue)
                if any(_prefix_match(t.norm, cn, table=self.table) or (len(cn) >= 5 and cn in t.norm) for t in toks) or (" " in cn and cn in sent):
                    scores[c] += 1
            w = salience.get(c, 0.0)
            scores[c] += 1.5 * w
            for other, ow in salience.items():
                if other != c and self.g.distance(c, other) == 1:
                    scores[c] += 1.5 * ow
            if sp is not None:
                d = self.g.distance(sp, c)
                scores[c] += 0.5 * max(0, 3 - d)
                younger = c in self.g.children[sp] or any(c in self.g.children[k] for k in self.g.children[sp]) or (c in self.g.siblings[sp] and self.g.is_elder(sp, c))
                if resp and not younger:
                    scores[c] += 1.0
                if inf and younger:
                    scores[c] += 1.0
        return max(cands, key=lambda c: (scores[c], -self.g.distance(sp, c) if sp is not None else 0))

    def _salience(self, context: list[str], speaker: str, listener: str) -> dict[int, float]:
        sal: dict[int, float] = {}
        for k, utt in enumerate(reversed(context[-6:])):
            w = 1.0 / (k + 1)
            for s in self.link(utt, speaker, listener, context=None):
                if s.node and s.type == "person":
                    pid = self.g.by_slug[s.node].id
                    sal[pid] = max(sal.get(pid, 0.0), w)
        return sal

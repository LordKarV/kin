"""Grounded translation: family-graph context + linked entities → Muse Spark structured output.

The family roster is the stable prefix of the system prompt (automatic prefix caching on Meta Model API);
only the per-utterance user message changes. A linker-only fallback keeps the call alive if the model fails.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache

from ..graph.kinship import FamilyGraph
from ..graph.linker import Linker, Span
from ..graph.kin_tables import load_table
from ..llm import LLM, StructuredOutputError, get_llm
from .pragmatics import filter_cards
from .schemas import GroundedSpan, TranslationOut

log = logging.getLogger("kin.mt")

LANG_NAMES = {"ta": "Tamil", "te": "Telugu", "hi": "Hindi", "es": "Spanish", "vi": "Vietnamese", "ml": "Malayalam", "kn": "Kannada"}

RULES = """You translate live speech between a grandparent and a grandchild, grounded on THIS family's people, places and foods.
Rules:
1. Render every linked kin term or name as the SPECIFIC person and their relation to the LISTENER. Never flatten a kin term to a generic English word ("uncle", "aunt", "grandma") when a linked family member exists. If two people share a name, say which one.
2. Keep every passthrough token in the source language verbatim (the listener already knows these words).
3. Emit a pragmatics card ONLY when a literal translation would lose meaning: idiom, proverb, honorific/register shift, or a cultural practice. Plain sentences get no card. A card needs source, literal, meaning, why_it_matters.
4. Output JSON matching the schema. The `translation` is spoken aloud: natural, brief English; use the family's own short forms ("Ravi mama", "your sister Divya") in speech and put the full disambiguation in grounded_spans.rendered, e.g. "your uncle Ravi mama (Mom's younger brother)". grounded_spans.node_id must be one of the ids in the roster.
5. Dish, place and event names stay as the family says them (rasam stays "rasam", never "soup"); add a 2-4 word gloss the first time if helpful.
6. Health, money or conflict content: translate faithfully, add nothing."""

GENERIC_RULES = """You are a translator. Translate the utterance (which may be in {lang}, romanized {lang}, or code-mixed with English) into natural, brief spoken English.
Output JSON matching the schema. grounded_spans may be empty. Emit a pragmatics card only when a literal translation would lose meaning (idiom, proverb, register); otherwise none. passthrough_kept is an empty list."""


@dataclass
class TranslateResult:
    result: TranslationOut
    spans: list[Span]
    passthrough: list[str]
    latencies: dict = field(default_factory=dict)
    error: str | None = None
    generic: bool = False

    def as_dict(self) -> dict:
        return {"translation": self.result.translation, "grounded_spans": [s.model_dump() for s in self.result.grounded_spans],
                "pragmatics_cards": [c.model_dump() for c in self.result.pragmatics_cards], "passthrough": self.passthrough,
                "confidence": self.result.confidence, "linker_spans": [s.as_dict() for s in self.spans], "latencies": self.latencies,
                "error": self.error}


class Translator:
    def __init__(self, graph: FamilyGraph, llm: LLM | None = None):
        self.g = graph
        self.linker = Linker(graph)
        self._llm = llm
        try:
            self.table = load_table(graph.heritage_lang)
        except (KeyError, FileNotFoundError):
            self.table = load_table("ta")
        self.lang = self.table.name
        self._system_cache: dict[str, str] = {}

    @property
    def llm(self) -> LLM:
        return self._llm or get_llm()

    # ---- prompts -------------------------------------------------------------
    def system_prompt(self, listener: str) -> str:
        if listener in self._system_cache:
            return self._system_cache[listener]
        li = self.g.by_slug[listener].id
        lines = [RULES, "", f"Heritage language: {self.lang}. Listener: {self.g.people[li].name} ({listener}).", "",
                 f"FAMILY ROSTER (relative to the listener {self.g.people[li].name}):"]
        for row in self.g.roster(li):
            extra = f" Also called: {', '.join(row['aliases'])}." if row["aliases"] else ""
            p = self.g.by_slug[row["id"]]
            by = f" b.~{p.birth_year}." if p.birth_year else ""
            dead = " (deceased)" if row["deceased"] else ""
            lines.append(f"- {row['id']}: {row['name']} ({row['lang_name']}) → {row['render']}{dead}.{by}{extra} {row['notes']}")
        lines += ["", "DISHES / PLACES / EVENTS (keep the family's names):"]
        for t in self.g.things:
            lines.append(f"- {t.slug} [{t.kind}]: {t.name} ({t.lang_name}); also {', '.join(a for a in t.aliases[:6])}. {t.note}")
        lines += ["", f"{self.lang.upper()} KIN TERMS: " + "; ".join(f"{d.term}={d.gloss}" for d in self.table.terms if d.kind == "kin")]
        s = "\n".join(lines)
        self._system_cache[listener] = s
        return s

    def user_prompt(self, text: str, speaker: str, listener: str, spans: list[Span], history, passthrough: list[str]) -> str:
        sp, li = self.g.by_slug[speaker], self.g.by_slug[listener]
        lines = [f"Speaker: {sp.name} ({self.g.render(li.id, sp.id)}). Listener: {li.name}."]
        if history:
            lines.append("Recent context (oldest first):")
            for who, src, tr in list(history)[-6:]:
                name = self.g.by_slug[who].name if who in self.g.by_slug else who
                lines.append(f"  {name}: {src}" + (f"  → {tr}" if tr else ""))
        linked = [s for s in spans if s.node]
        if linked:
            lines.append("Linked entities in this utterance (from the family graph; trust these unless context clearly contradicts):")
            for s in linked:
                amb = f" [confidence {s.confidence:.2f}; other candidates: {', '.join(c for c in s.candidates if c != s.node)}]" if s.confidence < 0.8 and len(s.candidates) > 1 else ""
                note = f" — {s.note}" if s.note else ""
                lines.append(f"  - '{s.source}' → {s.node}: {s.display}{note}{amb}")
        generic = [s for s in spans if not s.node and s.type == "kin"]
        if generic:
            lines.append("Kin words used generically here (NOT a relative): " + ", ".join(f"'{s.source}'" for s in generic))
        if passthrough:
            lines.append("Passthrough tokens (keep verbatim in the source language): " + ", ".join(passthrough))
        lines.append(f"Utterance: {text}")
        return "\n".join(lines)

    # ---- translation ---------------------------------------------------------
    def translate(self, text: str, speaker: str, listener: str, history=(), passthrough=(), reasoning_effort: str | None = None,
                  target_lang: str = "en") -> TranslateResult:
        t0 = time.perf_counter()
        ctx = [src for _who, src, _tr in history]
        spans = self.linker.link(text, speaker, listener, context=ctx)
        t_link = (time.perf_counter() - t0) * 1000
        # Fade guardrail: never pass through a token inside a grounded span
        safe_pt = [p for p in passthrough if not any(p in s.source or s.source in p for s in spans if s.node)]
        system = self.system_prompt(listener)
        user = self.user_prompt(text, speaker, listener, spans, history, safe_pt)
        if target_lang != "en":
            tl = LANG_NAMES.get(target_lang, target_lang)
            user += f"\nTarget language: {tl}. The listener speaks {tl}; translate INTO {tl} (natural spoken {tl}, Tamil script), keeping names and kin terms the family uses."
        t1 = time.perf_counter()
        error = None
        try:
            out = self.llm.structured(TranslationOut, system=system, user=user, reasoning_effort=reasoning_effort, max_completion_tokens=3000)
            out.pragmatics_cards = filter_cards(out.pragmatics_cards, text)
            out.grounded_spans = self._reconcile(out.grounded_spans, spans, listener)
        except Exception as e:  # StructuredOutputError, API errors, timeouts → linker-only fallback keeps the call alive
            log.warning("grounded translation failed (%s); using linker-only fallback", e)
            error = f"{type(e).__name__}: {e}"
            out = self.fallback(text, spans)
        t_mt = (time.perf_counter() - t1) * 1000
        return TranslateResult(out, spans, safe_pt, {"link_ms": round(t_link, 1), "mt_ms": round(t_mt, 1), "total_ms": round((time.perf_counter() - t0) * 1000, 1)}, error)

    @staticmethod
    def generic_user_prompt(text: str, speaker_name: str | None = None, listener_name: str | None = None, context: list[str] = ()) -> str:
        """Fair baseline: the same speaker/listener/context the grounded prompt gets, minus the family graph."""
        lines = []
        if speaker_name or listener_name:
            lines.append(f"Speaker: {speaker_name or 'unknown'}. Listener: {listener_name or 'unknown'}.")
        if context:
            lines.append("Recent context (oldest first):")
            lines += [f"  {c}" for c in list(context)[-6:]]
        lines.append(f"Utterance: {text}")
        return "\n".join(lines)

    def translate_generic(self, text: str, reasoning_effort: str | None = None, speaker: str | None = None, listener: str | None = None, history=()) -> TranslateResult:
        t0 = time.perf_counter()
        error = None
        name = lambda slug: self.g.by_slug[slug].name if slug in self.g.by_slug else slug  # noqa: E731
        ctx = [src for _who, src, _tr in history]
        try:
            out = self.llm.structured(TranslationOut, system=GENERIC_RULES.format(lang=self.lang),
                                      user=self.generic_user_prompt(text, name(speaker) if speaker else None, name(listener) if listener else None, ctx),
                                      reasoning_effort=reasoning_effort, max_completion_tokens=3000)
            out.pragmatics_cards = filter_cards(out.pragmatics_cards, text)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            out = TranslationOut(translation="", grounded_spans=[], pragmatics_cards=[], passthrough_kept=[], confidence=0.0)
        return TranslateResult(out, [], [], {"mt_ms": round((time.perf_counter() - t0) * 1000, 1)}, error, generic=True)

    def fallback(self, text: str, spans: list[Span]) -> TranslationOut:
        """Linker-only rendering: entities replaced by their listener-relative rendering; the rest untranslated."""
        pieces, pos = [], 0
        for s in sorted((s for s in spans if s.node), key=lambda s: s.start):
            pieces.append(text[pos:s.start]); pieces.append(s.display); pos = s.end
        pieces.append(text[pos:])
        return TranslationOut(translation="".join(pieces).strip(), grounded_spans=[GroundedSpan(source=s.source, rendered=s.display, node_id=s.node) for s in spans if s.node],
                              pragmatics_cards=[], passthrough_kept=[], confidence=0.3)

    def _reconcile(self, model_spans: list[GroundedSpan], linker_spans: list[Span], listener: str) -> list[GroundedSpan]:
        """Keep the model's spans but make sure every confidently linked entity is represented with a valid node id."""
        valid = set(self.g.by_slug) | set(self.g.thing_by_slug)
        out = [s for s in model_spans if s.node_id in valid]
        have = {s.node_id for s in out}
        for s in linker_spans:
            if s.node and s.node not in have and s.confidence >= 0.85:
                out.append(GroundedSpan(source=s.source, rendered=s.display, node_id=s.node))
                have.add(s.node)
        return out


@lru_cache(maxsize=4)
def _cached_graph(family_id: int) -> FamilyGraph:
    from ..db.session import session_scope
    with session_scope() as s:
        return FamilyGraph.from_session(s, family_id)


def get_translator(family_id: int) -> Translator:
    return Translator(_cached_graph(family_id))


def reset_translator_cache() -> None:
    _cached_graph.cache_clear()

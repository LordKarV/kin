#!/usr/bin/env python3
"""Multi-language end-to-end check: KIN's common-ground cards and translation in each Muse Voice Transcribe language,
plus (with --asr) Muse speech recognition of a synthesized line. It drives a running server the way
scripts/demo_common_ground.py does (dev clock, users, LiveKit legs, typed lines on POST /api/calls/{id}/text, data
messages on topic "kin") and reuses its Demo and Leg.

Per language L, with fresh users A (English) and B (speaks L), lines from scripts/multilang_lines.json:
  0. Clock -42. A's friend Mei is planted as A's own tie fact, heard by nobody (POST /api/dev/apply, as the demo plants
     Arjun's facts): B's card about Mei in step 4 needs it.
  1. Call 1: B introduces a new friend in L, then both hang up so the call-end extraction runs. GET /api/world as A is
     polled until the friend appears; that person's slug keys the checks below.
       extract    a new person shows up in A's world within --extract-timeout
  2. Clock 0, call 2: B mentions the friend again.
       card       A gets a "who" card about the friend (gap shown; expected "reminder": A heard of them 42 days ago)
       caption    A's English caption names the friend (a Latin form from the data file, or the extracted name)
  3. B repeats that line.
       silent     A gets no further card about the friend
  4. A says "My friend Mei and I went hiking last weekend."
       mei_l10n   B gets a who card about Mei whose body (after its glance_update, if one comes) is in L: L's script
                  (kin_tables.SCRIPT) for non-Latin languages; for Latin ones, not the English body and not English by
                  a stopword count
       b_caption  B's caption of the line is in L, by the same test
     Over all of call 2:
       b_quiet    B gets no card about their own friend
  5. --asr: the call-2 line is synthesized with the app's TTS (ElevenLabs pcm_16000 is already 16 kHz mono PCM16, so no
     conversion) and streamed in real time into the app's Muse ASR client, built as the pipeline builds it:
     make_asr(L, keyterms), so languageBias [<L name>, "English"] and keywords = the Latin forms of B, A and the
     friend (LiveWorld.keyterms passes only Latin forms).
       asr_cer    a final transcript with character error rate <= --cer-max (punctuation and spaces removed)
       asr_name   the friend's name (any form) is in the transcript
     A blocked TTS or ASR (no key, mock provider, language rejected) is SKIP, "not run", never PASS.

Cost: see cost_note() (printed first). Needs what the demo driver needs: DEV_ENDPOINTS=1, MODEL_API_KEY,
`livekit-server --dev`. Reruns on one database are fine (names carry a per-run tag, no phone is sent). The dev clock is
global: run nothing else on the server meanwhile.

    backend/.venv/bin/python scripts/multilang_check.py --dry-run --langs all
    cd backend && .venv/bin/python ../scripts/multilang_check.py [--langs es,ja | all] [--asr] [--out FILE]

Env: KIN_BASE (default http://127.0.0.1:8000), KIN_KEY. Exits 1 when any check fails or a language errors.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import string
import sys
import time
import unicodedata
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
os.environ.setdefault("KIN_BASE", "http://127.0.0.1:8000")  # before the import: the demo driver reads it at import

import httpx  # noqa: E402

import demo_common_ground as demo  # noqa: E402
from app.graph.kin_tables import MUSE_LANGUAGES, SCRIPT  # noqa: E402  (pure: no settings, DB or network)
from app.world.match import AliasIndex, fold, script_of  # noqa: E402

LINES = HERE / "multilang_lines.json"
OUT = Path("/private/tmp/claude-501/-Users-karthikvattem-projects-hacktx/747c8ac2-96df-481f-b12c-50ff512a5dea/"
           "scratchpad/multilang.md")
DEFAULT_LANGS = "es,fr,de,pt,hi,bn,ar,he,ja,ko,th,vi,tr,id,ta,zh"
CALL1_DAY, CALL2_DAY = -42, 0
# LiveWorld.close stamps the call-1 knowledge with clock.now() right after the extraction commits. Moving the clock
# before that would date A's "heard" at day 0, and call 2 would then show no card at all.
FLUSH_GRACE_S = 2.0
SR, FRAME_BYTES = 16000, 640  # 20 ms frames of 16 kHz PCM16, what rtc/agent.py feeds the ASR
TTS_TIMEOUT_S, ASR_START_S, ASR_DRAIN_S = 30.0, 15.0, 3.0
EN_WORDS = frozenset("the and my i went with last weekend friend from is of to s first mentioned her his she he we "
                     "was".split())
CHECKS = (("extract", "friend extracted"), ("card", "A card c2"), ("caption", "A caption name"),
          ("silent", "repeat silent"), ("b_quiet", "B no own card"), ("mei_l10n", "Mei card in L"),
          ("b_caption", "B caption in L"), ("asr_cer", "ASR CER"), ("asr_name", "ASR name"))
LAT_COLS = (("card_ms", "card ms"), ("caption_ms", "caption ms"), ("mt_ms", "mt ms"), ("b_card_ms", "Mei card ms"),
            ("l10n_ms", "l10n ms"))
FAILING = ("FAIL", "ERR")


# ---- text helpers ----------------------------------------------------------------------------------------------------
def is_latin(form: str) -> bool:
    """app.world.live._latin, the filter LiveWorld.keyterms applies (live.py itself pulls in the DB layer)."""
    letters = [c for c in form if c.isalpha()]
    return bool(letters) and all(script_of(c) == "latin" for c in letters)


def _folded(s: str) -> str:
    return " ".join(fold(s)[0].split())


def name_found(text: str, forms: list[str]) -> bool:
    """A Latin form as a whole word, with or without its inner space or hyphen (Ji-woo, Jiwoo); a form in another
    script as a substring, since Chinese, Japanese and Thai have no spaces."""
    t = _folded(text)
    for form in forms:
        f = _folded(form)
        if not f:
            continue
        if not is_latin(form):
            if f.replace(" ", "") in t.replace(" ", ""):
                return True
        elif any(re.search(rf"(?<!\w){re.escape(v)}(?!\w)", t) for v in {f, f.replace(" ", "")}):
            return True
    return False


def looks_english(text: str) -> bool:
    # ponytail: stopword share; tells an untranslated body from a Latin-script translation, not dialects or code-mixing
    words = re.findall(r"[a-z]+", text.lower())
    hits = sum(w in EN_WORDS for w in words)
    return hits >= 2 and hits >= 0.34 * len(words)


def in_lang(lang: str, text: str, english: str = "") -> bool:
    if not text.strip():
        return False
    if SCRIPT.get(lang):
        return re.search(SCRIPT[lang], text) is not None
    return text.strip() != english.strip() and not looks_english(text)


def _chars(s: str) -> list[str]:
    return [c for c in unicodedata.normalize("NFC", s).casefold() if unicodedata.category(c)[0] not in "PZC"]


def levenshtein(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    r = _chars(ref)
    return levenshtein(r, _chars(hyp)) / max(1, len(r))


def precheck(lang: str, spec: dict) -> str:
    """Offline: the server's alias matcher (AliasIndex.scan with L's suffixes) over the call-2 line, indexing the data
    file's forms. The live index holds the forms the extraction chose, so this predicts, it does not prove."""
    hits = AliasIndex((f, "person", 1) for f in spec["friend"]["forms"]).scan(spec["call2"]["text"], lang)
    return f"hit {[h.surface for h in hits]}" if hits else "MISS: no alias hit on the call-2 line, so no card"


# ---- messages --------------------------------------------------------------------------------------------------------
def ms(at: float | None, t0: float) -> float | None:
    return None if at is None else round((at - t0) * 1000)


def glance_items(msgs: list[dict]) -> list[tuple[dict, float]]:
    return [(it, m["_at"]) for m in msgs if m.get("type") == "glance" for it in m.get("items", [])]


def caption(msgs: list[dict], listener: str) -> dict | None:
    return next((m for m in msgs if m.get("type") == "transcript" and m.get("listener") == listener), None)


def server_latency(msgs: list[dict]) -> dict:
    lat = [m for m in msgs if m.get("type") == "latency"]
    return lat[-1].get("latencies", {}) if lat else {}


def describe(m: dict) -> str | None:
    t = m.get("type")
    if t == "transcript":
        if m.get("listener") is None:
            return None  # the speaker's own line echoed back
        return f"caption: {m.get('translation')!r}" + (f" [mt error: {m['error']}]" if m.get("error") else "")
    if t == "glance":
        cards = "; ".join(f"card [{it.get('kind')}{'/' + it['gap'] if it.get('gap') else ''}] {it.get('title', '')}: "
                          f"{it.get('body', '')}" for it in m.get("items", []))
        return cards + (" (partial)" if m.get("partial") else "")
    if t == "glance_update":
        return f"localized {m.get('key')}: {m.get('body')}"
    if t == "glance_retract":
        return f"glance_retract {m.get('keys')}"
    if t == "enrich" and m.get("pragmatics_cards"):
        return "culture cards: " + json.dumps(m["pragmatics_cards"], ensure_ascii=False)[:300]
    if t == "error":
        return f"error ({m.get('stage')}): {m.get('message')}"
    if t == "status" and m.get("asr") != "ok":
        return f"status asr={m.get('asr')}: {m.get('detail', '')}"
    return None


@dataclass
class Report:
    lang: str
    checks: dict[str, tuple[str, str]] = field(default_factory=dict)
    lat: dict[str, float | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    msgs: list[dict] = field(default_factory=list)
    gap: str = ""
    error: str = ""

    def say(self, line: str) -> None:
        self.notes.append(line)
        print(line)

    def heard(self, title: str, line: dict, got: dict[str, list[dict]], t0: float) -> None:
        """One line and what each person received, with arrival times from the moment the line was posted."""
        self.say(f"- {title}: `{line['text']}` ({line['gloss']})")
        for who, msgs in got.items():
            self.msgs.extend(msgs)
            seen = [(d, m["_at"]) for m in msgs if (d := describe(m))]
            for d, at in seen or [("nothing", None)]:
                self.say(f"  - {who} got {d}" + (f" (+{ms(at, t0)} ms)" if at is not None else ""))


# ---- driver ----------------------------------------------------------------------------------------------------------
class _Stamped(list):
    """Leg.connect's data handler appends each decoded message here: stamp its arrival for the latency columns."""

    def append(self, msg) -> None:
        super().append({**msg, "_at": time.perf_counter()} if isinstance(msg, dict) else msg)


class TimedLeg(demo.Leg):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.msgs = _Stamped()

    def take(self) -> list[dict]:
        out, self.msgs = list(self.msgs), _Stamped()
        return out


class Runner(demo.Demo):
    """The demo driver's HTTP helpers (post, json, clock, apply) plus a GET, a timed typed line and a call context."""

    def __init__(self, http: httpx.AsyncClient, wait_s: float) -> None:
        super().__init__(http, wait_s)
        self.names: dict[str, str] = {}

    async def get(self, path: str, who: str) -> dict:
        try:
            r = await self.http.get(path, headers={"X-KIN-User": self.token[who]})
        except httpx.HTTPError as e:
            raise demo.HttpError(f"GET {path}: {type(e).__name__}: {e}") from e
        if r.status_code >= 400:
            raise demo.HttpError(f"GET {path}: HTTP {r.status_code}: {r.text[:400]}")
        return r.json()

    async def type_line(self, call_id: int, who: str, text: str) -> float:
        """Demo.say's retry (409 until the KIN agent has joined `who`); returns when the accepted POST started."""
        for _ in range(demo.JOIN_TRIES):
            t0 = time.perf_counter()
            r = await self.post(f"/api/calls/{call_id}/text", {"text": text}, who, ok409=True)
            if r.status_code != 409:
                return t0
            await asyncio.sleep(demo.JOIN_RETRY_S)
        raise demo.HttpError(f"call {call_id}: {who} never joined on the server side (409 {r.text[:200]})")

    @asynccontextmanager
    async def in_call(self, a: str, b: str):
        """Demo.call with timed legs. Both hang up on the way out, which ends the call and starts its extraction."""
        ja = await self.json("/api/rtc/join", {}, a)
        jb = await self.json("/api/rtc/join", {"call_id": ja["call_id"], "invite": ja["invite"]}, b)
        legs: dict[str, TimedLeg] = {}
        try:
            legs[a] = await TimedLeg(a).connect(ja)
            legs[b] = await TimedLeg(b).connect(jb)
            yield ja["call_id"], legs
        finally:
            for leg in legs.values():
                try:
                    await leg.hang_up()
                except Exception as e:  # noqa: BLE001  a failed hang-up must not hide the step's own error
                    print(f"  ! {leg.name}: hang up failed: {e}", file=sys.stderr)


async def make_users(d: Runner, langs: list[str], data: dict, tag: str) -> dict[str, str]:
    """Every B first, then every A: each language new to the space makes a FormsOut call per existing user
    (api/users.py _new_lang_others), and this order keeps that fan-out at n(n-1)/2. Returns lang -> sign-up error."""
    errors: dict[str, str] = {}
    people = [(f"B-{L}", f"{data['langs'][L]['speaker']} {tag}", L, L) for L in langs]
    people += [(f"A-{L}", f"Sam {tag}-{L}", "en", L) for L in langs]
    for key, name, lang, for_lang in people:
        if for_lang in errors:
            continue
        try:
            out = await d.json("/api/users", {"name": name, "lang": lang, "phone": None})
        except demo.HttpError as e:
            errors[for_lang] = f"sign-up of {name} failed: {e}"
            continue
        d.token[key], d.slug[key], d.names[key] = out["token"], out["person"], name
        print(f"user {name} ({lang}) -> {out['person']}")
    return errors


async def plant_mei(d: Runner, a: str, mei: dict) -> str:
    """A's friend Mei as A's own tie fact, heard by nobody (demo_common_ground.plant_arjun's pattern). When A names Mei
    on a call, that fact is what lets B's card say who she is (visibility.disclosable)."""
    name, ctx = mei["name"], mei["context"]
    entity = {"ref": "mei", "name": name, "native": "", "forms": [name], "kind": "person", "existing_id": None}
    out = await d.apply(a, [], {
        "entities": [entity],
        "ties": [{"a": "speaker", "b": "mei", "kind": "friend", "context": ctx}],
        "facts": [demo._fact("speaker", "tie", f"{name} is {d.names[a]}'s friend {ctx}", ["mei"], [])]})
    return next(e["slug"] for e in out["entities"] if e["ref"] == "mei")


async def wait_friend(d: Runner, a: str, before: set[str], forms: list[str],
                      timeout: float) -> tuple[dict | None, float, list[dict]]:
    """Poll A's world until the call-1 extraction adds a person (the friend, preferably by name)."""
    t0 = time.perf_counter()
    while True:
        new = [p for p in (await d.get("/api/world", a))["people"] if not p["is_user"] and p["person"] not in before]
        if new:
            pick = next((p for p in new if name_found(f"{p['name']} {p['render']}", forms)), new[0])
            return pick, time.perf_counter() - t0, new
        if time.perf_counter() - t0 > timeout:
            return None, timeout, []
        await asyncio.sleep(1.0)


async def run_lang(d: Runner, L: str, data: dict, args: argparse.Namespace, rep: Report) -> None:
    spec, a_line = data["langs"][L], data["a_line"]
    A, B = f"A-{L}", f"B-{L}"
    forms = spec["friend"]["forms"]
    rep.say(f"- users: A {d.names[A]} ({d.slug[A]}, en), B {d.names[B]} ({d.slug[B]}, {L}); "
            f"matcher precheck: {precheck(L, spec)}")
    await d.clock(CALL1_DAY)
    mei_slug = await plant_mei(d, A, data["mei"])
    before = {p["person"] for p in (await d.get("/api/world", A))["people"]}

    async with d.in_call(A, B) as (cid, legs):
        t = await d.type_line(cid, B, spec["call1"]["text"])
        await asyncio.sleep(args.wait)
        rep.heard(f"call {cid} (day {CALL1_DAY}), B says", spec["call1"], {"A": legs[A].take(), "B": legs[B].take()}, t)

    friend, secs, new = await wait_friend(d, A, before, forms, args.extract_timeout)
    if friend is None:
        rep.checks["extract"] = ("FAIL", f"no new person in A's world {args.extract_timeout:.0f} s after call 1")
    else:
        others = [p["name"] for p in new if p is not friend]
        rep.checks["extract"] = ("PASS", f"{friend['name']} ({friend['person']}) after {secs:.1f} s, A sees "
                                         f"{friend['render']!r}" + (f"; also new: {others}" if others else ""))
    rep.say(f"- extraction: {rep.checks['extract'][1]}")
    await asyncio.sleep(FLUSH_GRACE_S)

    await d.clock(CALL2_DAY)
    steps: list[tuple[float, dict[str, list[dict]]]] = []
    async with d.in_call(A, B) as (cid, legs):
        for title, who, line in ((f"call {cid} (day {CALL2_DAY}), B says", B, spec["call2"]),
                                 ("same call, B repeats", B, spec["call2"]), ("same call, A says", A, a_line)):
            t = await d.type_line(cid, who, line["text"])
            await asyncio.sleep(args.wait)
            got = {"A": legs[A].take(), "B": legs[B].take()}
            rep.heard(title, line, got, t)
            steps.append((t, got))
    evaluate(rep, L, spec, a_line["text"], friend, mei_slug, d.slug[A], d.slug[B], steps)
    if args.asr:
        names = (d.names[B], d.names[A], *([friend["name"]] if friend else []), *forms)
        keyterms = list(dict.fromkeys(n for n in names if is_latin(n)))[:100]  # LiveWorld.keyterms: Latin forms, 100
        cer_c, name_c, notes = await asr_check(L, spec["call2"]["text"], forms + ([friend["name"]] if friend else []),
                                               keyterms, args)
        rep.checks["asr_cer"], rep.checks["asr_name"] = cer_c, name_c
        for n in notes:
            rep.say(n)


def evaluate(rep: Report, L: str, spec: dict, a_text: str, friend: dict | None, mei_slug: str, a_slug: str,
             b_slug: str, steps: list[tuple[float, dict[str, list[dict]]]]) -> None:
    (t2, s2), (_t3, s3), (t4, s4) = steps
    slug = friend["person"] if friend else None
    forms = spec["friend"]["forms"] + ([friend["name"]] if friend else [])

    def about(it: dict, who_slug: str | None) -> bool:
        return who_slug is not None and who_slug in (it.get("node_id"), it.get("key", "").partition(":")[2])

    def about_friend(it: dict) -> bool:  # by slug, or by name for an ask card (its key is the folded name)
        return about(it, slug) or name_found(it.get("title", ""), forms)

    cards = [(it, at) for it, at in glance_items(s2["A"]) if about_friend(it)]
    who = [(it, at) for it, at in cards if it.get("kind") == "who"]
    if who:
        it, at = who[0]
        rep.gap = it.get("gap") or ""
        note = "" if rep.gap == "reminder" else " (expected a reminder: A heard of the friend 42 days ago)"
        rep.checks["card"] = ("PASS", f"[{rep.gap}] {it.get('title')}: {it.get('body')}{note}")
        rep.lat["card_ms"] = ms(at, t2)
    else:
        rep.checks["card"] = ("FAIL", f"only {[c.get('kind') for c, _ in cards]} card(s) about the friend" if cards
                              else "no card about the friend")
    latin = [f for f in forms if is_latin(f)]
    cap = caption(s2["A"], a_slug)
    if cap is None:
        rep.checks["caption"] = ("FAIL", "no caption")
    else:
        text = cap.get("translation") or ""
        rep.checks["caption"] = ("PASS" if name_found(text, latin) else "FAIL", f"{text!r} (looked for {latin})")
        rep.lat["caption_ms"] = ms(cap["_at"], t2)
    rep.lat["mt_ms"] = server_latency(s2["A"]).get("mt_ms")
    again = [it for it, _ in glance_items(s3["A"]) if about_friend(it)]
    rep.checks["silent"] = (("FAIL", f"{[(c.get('kind'), c.get('title')) for c in again]}") if again
                            else ("PASS", "no card about the friend"))
    own = [it for _t, s in steps for it, _ in glance_items(s["B"]) if about_friend(it)]
    rep.checks["b_quiet"] = (("FAIL", f"{[(c.get('kind'), c.get('title')) for c in own]}") if own
                             else ("PASS", "no card about the friend"))

    mei = [(it, at) for it, at in glance_items(s4["B"]) if about(it, mei_slug)]
    if not mei:
        got = [(c.get("kind"), c.get("title")) for c, _ in glance_items(s4["B"])]
        rep.checks["mei_l10n"] = ("FAIL", f"no card about Mei (B got {got})")
    else:
        it, at = mei[0]
        upd = next((m for m in s4["B"] if m.get("type") == "glance_update" and m.get("key") == it.get("key")), None)
        body = (upd or it).get("body", "")
        english = it.get("body", "") if upd else ""
        how = f"English first: {english!r}" if upd else "arrived localized (prewarmed)"
        rep.checks["mei_l10n"] = ("PASS" if in_lang(L, body, english) else "FAIL", f"{body!r} ({how})")
        rep.lat["b_card_ms"] = ms(at, t4)
        rep.lat["l10n_ms"] = ms(upd["_at"] if upd else at, t4)
    capb = caption(s4["B"], b_slug)
    if capb is None:
        rep.checks["b_caption"] = ("FAIL", "no caption")
    else:
        text = capb.get("translation") or ""
        rep.checks["b_caption"] = ("PASS" if in_lang(L, text, a_text) else "FAIL", repr(text))
    kinds = [m.get("type") for m in rep.msgs]
    asks = sum(it.get("kind") == "ask" for it, _ in glance_items(rep.msgs))
    rep.say(f"- totals: {kinds.count('error')} error message(s), {asks} ask card(s), "
            f"{kinds.count('glance_retract')} glance_retract(s); server latencies of B's call-2 line: "
            f"{server_latency(s2['A'])}")


# ---- speech recognition (--asr) --------------------------------------------------------------------------------------
async def _feed(asr, pcm: bytes, final: asyncio.Event, tail_s: float) -> None:
    """Real time, as rtc/agent.py _pump does it: 20 ms frames on a sample clock (Muse closes a stream fed faster or
    slower than real time), then silence like its DTX filler (Muse ends a turn only after hearing silence) until a
    final arrives after the last word, or tail_s runs out."""
    loop = asyncio.get_running_loop()
    start, sent = loop.time(), 0
    speech, total = len(pcm), len(pcm) + int(tail_s * SR) * 2
    while sent < total:
        if sent >= speech and final.is_set():
            return
        if sent < speech <= sent + FRAME_BYTES:
            final.clear()  # a turn that ended mid-sentence does not end the line: wait for the one after the last word
        await asr.send_audio(pcm[sent:sent + FRAME_BYTES].ljust(FRAME_BYTES, b"\0"))
        sent += FRAME_BYTES
        ahead = start + sent / 2 / SR - loop.time()
        if ahead > 0:
            await asyncio.sleep(ahead)


async def asr_check(lang: str, text: str, forms: list[str], keyterms: list[str],
                    args: argparse.Namespace) -> tuple[tuple[str, str], tuple[str, str], list[str]]:
    from app.audio.asr import make_asr  # lazy: --dry-run and runs without --asr never load settings or providers
    from app.audio.tts import MockTTS, get_tts
    from app.config import get_settings

    s, tts = get_settings(), get_tts()
    blocked = (f"ASR_PROVIDER is {s.asr_provider!r}, not muse" if s.asr_provider != "muse"
               else "no MODEL_API_KEY for Muse" if not s.model_api_key
               else "TTS is the mock tone (no ELEVENLABS_API_KEY, or TTS_PROVIDER=mock)" if isinstance(tts, MockTTS)
               else "")
    if blocked:
        return ("SKIP", blocked), ("SKIP", blocked), [f"- ASR not run: {blocked}"]
    try:
        async with asyncio.timeout(TTS_TIMEOUT_S):  # pcm_16000 (tts.elevenlabs_request): 16 kHz mono PCM16 LE as is
            pcm = b"".join([c async for c in tts.stream(text, voice_id="", language_code=lang)])
    except Exception as e:  # noqa: BLE001  a language ElevenLabs rejects is a finding, and it blocks this check
        why = f"TTS failed for {lang}: {type(e).__name__}: {e}"[:300]
        return ("SKIP", why), ("SKIP", why), [f"- ASR not run: {why}"]
    pcm = pcm[: len(pcm) // 2 * 2]
    if not pcm:
        why = f"TTS returned no audio for {lang}"
        return ("SKIP", why), ("SKIP", why), [f"- ASR not run: {why}"]
    asr = make_asr(language=lang, keyterms=keyterms)
    finals: list[str] = []
    partials: list[str] = []
    final = asyncio.Event()

    async def read() -> None:
        async for ev in asr.events():
            (finals if ev.final else partials).append(ev.text)
            if ev.final:
                final.set()

    reader: asyncio.Task | None = None
    try:
        async with asyncio.timeout(ASR_START_S):
            await asr.start()
        reader = asyncio.create_task(read())
        await _feed(asr, pcm, final, args.asr_tail)
    except Exception as e:  # noqa: BLE001
        why = f"Muse ASR failed: {type(e).__name__}: {e}"[:300]
        return ("ERR", why), ("ERR", why), [f"- ASR: {why}"]
    finally:
        await asr.finish()
        if reader is not None:
            try:
                async with asyncio.timeout(ASR_DRAIN_S):
                    await reader
            except TimeoutError:
                reader.cancel()
    hyp = " ".join(finals) or (partials[-1] if partials else "")
    got = "final" if finals else ("partial only" if partials else "nothing")
    c = cer(text, hyp)
    notes = [f"- ASR: {len(pcm) / 2 / SR:.1f} s of TTS audio, languageBias [{MUSE_LANGUAGES[lang]!r}, 'English'], "
             f"keywords {keyterms}: {got} {hyp!r}, CER {c:.2f}"]
    return (("PASS" if finals and c <= args.cer_max else "FAIL", f"{c:.2f} ({got}): {hyp!r}"),
            ("PASS" if name_found(hyp, forms) else "FAIL", f"looked for {forms} in {hyp!r}"), notes)


# ---- run -------------------------------------------------------------------------------------------------------------
async def run_guarded(d: Runner, L: str, data: dict, args: argparse.Namespace, setup_error: str | None) -> Report:
    rep = Report(L)
    rep.say(f"\n## {L} ({MUSE_LANGUAGES[L]})")
    if setup_error:
        rep.error = setup_error
    else:
        try:
            async with asyncio.timeout(args.lang_timeout):
                await run_lang(d, L, data, args, rep)
        except TimeoutError:
            rep.error = f"timed out after {args.lang_timeout:.0f} s"
        except demo.HttpError as e:  # a SystemExit subclass: caught here so one language cannot end the run
            rep.error = str(e)
        except Exception as e:  # noqa: BLE001  each language runs independently
            rep.error = f"{type(e).__name__}: {e}"
    if rep.error:
        rep.say(f"- ERROR: {rep.error}")
    for key, _label in CHECKS:
        if key not in rep.checks and (args.asr or not key.startswith("asr")):
            rep.checks[key] = ("ERR", f"not reached: {rep.error}") if rep.error else ("SKIP", "not run")
    return rep


async def run(args: argparse.Namespace, data: dict, langs: list[str]) -> tuple[list[Report], str]:
    headers = {"X-KIN-Key": demo.KEY} if demo.KEY else {}
    tag = secrets.choice(string.ascii_uppercase) + "".join(secrets.choice(string.ascii_lowercase) for _ in range(2))
    reports: list[Report] = []
    async with httpx.AsyncClient(base_url=demo.BASE, headers=headers, timeout=30.0) as http:
        d = Runner(http, args.wait)
        try:
            errors = await make_users(d, langs, data, tag)
            if args.settle > 0:
                print(f"\nwaiting {args.settle:.0f} s for the sign-up name-form calls to drain")
                await asyncio.sleep(args.settle)
            for L in langs:
                reports.append(await run_guarded(d, L, data, args, errors.get(L)))
        except demo.HttpError as e:
            return reports, str(e)
        finally:
            try:
                await d.clock(0)
            except demo.HttpError as e:
                print(f"! could not reset the dev clock: {e}", file=sys.stderr)
    return reports, ""


# ---- output ----------------------------------------------------------------------------------------------------------
def cost_note(n: int, args: argparse.Namespace) -> str:
    asr = f" --asr adds {n} ElevenLabs requests and {n} Muse ASR streams." if args.asr else ""
    return (f"Cost, read from the code (not measured): about {13 * n} LLM calls for {n} language(s). Per language: 4 "
            "lines x 2 MT calls (call A and call B, +1 when call A is slow enough to hedge), 2 call-end extractions, "
            "1-2 card localizations, 2 sign-up name-form calls. On top, about "
            f"{n * (n - 1) // 2} FormsOut calls from the sign-up fan-out (each language new to the space asks for "
            "name forms of every existing user, api/users.py _new_lang_others; more if the space already has users). "
            "Every call join also opens a Muse ASR stream per person (4 per language) though nothing is spoken; no "
            f"TTS (voice stays off).{asr} Time: about {max(1, round(n * (4 * args.wait + 30) / 60))} min.")


def table(reports: list[Report], args: argparse.Namespace) -> str:
    cols = [(k, label) for k, label in CHECKS if args.asr or not k.startswith("asr")]
    head = ["lang", *(label for _k, label in cols), *(label for _k, label in LAT_COLS)]
    rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in reports:
        cells = [r.checks[k][0] + (f" ({r.gap})" if k == "card" and r.gap else "") for k, _l in cols]
        lat = ["" if r.lat.get(k) is None else f"{r.lat[k]:.0f}" for k, _l in LAT_COLS]
        rows.append("| " + " | ".join([r.lang, *cells, *lat]) + " |")
    tally = [st for r in reports for st, _d in r.checks.values()]
    rows.append(f"\n{tally.count('PASS')} pass, {tally.count('FAIL')} fail, {tally.count('ERR')} error, "
                f"{tally.count('SKIP')} not run (SKIP is never a pass)")
    return "\n".join(rows)


def render(reports: list[Report], args: argparse.Namespace, fatal: str, started: str, langs: list[str]) -> str:
    out = ["# KIN multi-language check", "",
           f"Run {started} against {demo.BASE}; languages {', '.join(langs)}; --wait {args.wait:g} s.", "",
           cost_note(len(langs), args), ""]
    if fatal:
        out += [f"FATAL: {fatal}", ""]
    out += [table(reports, args), "", "Latencies are from posting the line to the message arriving on the LiveKit leg; "
            "mt ms is the server's own MT time for B's call-2 line.", ""]
    for r in reports:
        out += r.notes + ["- checks:"] + [f"  - {k}: {st}: {detail}" for k, (st, detail) in r.checks.items()] + [""]
    return "\n".join(out)


def plan(langs: list[str], data: dict, args: argparse.Namespace) -> str:
    out = [cost_note(len(langs), args), ""]
    for L in langs:
        spec, name = data["langs"][L], MUSE_LANGUAGES[L]
        f = spec["friend"]
        latin = [x for x in f["forms"] if is_latin(x)]
        test = f"script {SCRIPT[L]}" if SCRIPT.get(L) else "not the English body, not English by stopwords"
        out += [f"## {L} ({name}): A 'Sam <tag>-{L}' (en), B '{spec['speaker']} <tag>' ({L}); friend {f['native']}, "
                f"Latin forms {latin}",
                f"  1. clock {CALL1_DAY}; plant Mei as A's friend {data['mei']['context']} (POST /api/dev/apply, heard "
                "by nobody)",
                f"  2. call 1, B: {spec['call1']['text']}", f"       ({spec['call1']['gloss']})",
                f"     hang up; poll GET /api/world as A for the friend (call-end extraction, up to "
                f"{args.extract_timeout:.0f} s)",
                f"  3. clock {CALL2_DAY}; call 2, B: {spec['call2']['text']}", f"       ({spec['call2']['gloss']})",
                "     expect: A gets a who card about the friend (reminder); A's caption names the friend; B gets no "
                "card about the friend all call",
                "  4. B repeats the line; expect: no new card about the friend for A",
                f"  5. A: {data['a_line']['text']}",
                f"     expect: B gets a who card about Mei, body in {name} ({test}); B's caption in {name}",
                f"  6. (--asr only) TTS of the call-2 line -> Muse ASR, languageBias [{name!r}, 'English'], keywords = "
                f"A and B names + {latin}; expect CER <= {args.cer_max:g} and the friend's name in the transcript",
                f"  matcher precheck (offline, data-file forms): {precheck(L, spec)}", ""]
    return "\n".join(out)


def load_lines(path: Path) -> tuple[dict, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    for L, spec in data["langs"].items():
        if L not in MUSE_LANGUAGES or L == "en":
            problems.append(f"{L}: not a non-English Muse language")
            continue
        native = _folded(spec["friend"]["native"])
        for call in ("call1", "call2"):
            text = spec[call]["text"]
            if native not in _folded(text):
                problems.append(f"{L} {call}: the friend's name {spec['friend']['native']!r} is not in the line")
            if SCRIPT.get(L) and not re.search(SCRIPT[L], text):
                problems.append(f"{L} {call}: not in {MUSE_LANGUAGES[L]} script")
            if not spec[call].get("gloss"):
                problems.append(f"{L} {call}: no English gloss")
    return data, problems


def pick_langs(arg: str, data: dict) -> list[str]:
    langs = sorted(c for c in MUSE_LANGUAGES if c != "en") if arg == "all" else [c.strip() for c in arg.split(",")
                                                                                  if c.strip()]
    bad = [c for c in langs if c not in data["langs"]]
    if bad:
        raise SystemExit(f"no lines for {bad} in {LINES.name} (Muse languages: {sorted(MUSE_LANGUAGES)})")
    return langs


def selfcheck() -> None:
    assert levenshtein(list("kitten"), list("sitting")) == 3
    assert cer("Hola, mundo.", "hola mundo") == 0.0 and cer("abcd", "abxd") == 0.25
    assert name_found("I went with Ji-woo", ["Jiwoo", "Ji-woo"]) and name_found("with Jiwoo", ["Ji-woo"])
    assert name_found("Bea and I", ["Bea"]) and not name_found("a beautiful beach", ["Bea"])
    assert name_found("昨日も由紀ちゃんと", ["由紀"]) and name_found("Lucia came", ["Lucía"])
    assert in_lang("ja", "メイさん") and not in_lang("ja", "Mei")
    assert looks_english("Sam's friend Mei (from college)")
    assert not looks_english("Mi amiga Mei y yo fuimos de excursión")
    assert not in_lang("es", "Sam's friend Mei (from college)") and in_lang("es", "Mei, amiga de Sam")
    print("self-check ok: CER, name and language tests")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--langs", default=DEFAULT_LANGS, help="comma list of codes, or 'all' (the 24 besides en)")
    ap.add_argument("--asr", action="store_true", help="also synthesize each call-2 line and run it through Muse ASR")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and the offline matcher precheck; no HTTP")
    ap.add_argument("--out", type=Path, default=OUT, help="markdown report path")
    ap.add_argument("--wait", type=float, default=10.0, help="seconds to collect messages after each line")
    ap.add_argument("--extract-timeout", type=float, default=60.0, help="seconds to wait for call 1's extraction")
    ap.add_argument("--lang-timeout", type=float, default=240.0, help="seconds per language before it is abandoned")
    ap.add_argument("--settle", type=float, default=15.0, help="seconds after sign-up for the name-form calls")
    ap.add_argument("--cer-max", type=float, default=0.3, help="highest passing ASR character error rate")
    ap.add_argument("--asr-tail", type=float, default=8.0, help="most seconds of silence fed after the speech")
    args = ap.parse_args()
    data, problems = load_lines(LINES)
    langs = pick_langs(args.langs, data)
    if problems:
        raise SystemExit("bad lines file:\n  " + "\n  ".join(problems))
    if args.dry_run:
        selfcheck()
        print(plan(langs, data, args))
        return
    started = datetime.now().isoformat(timespec="seconds")
    print(cost_note(len(langs), args))
    reports, fatal = asyncio.run(run(args, data, langs))
    md = render(reports, args, fatal, started, langs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    print("\n" + (f"FATAL: {fatal}\n" if fatal else "") + table(reports, args) + f"\n\nreport: {args.out}")
    failed = fatal or any(st in FAILING for r in reports for st, _d in r.checks.values())
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

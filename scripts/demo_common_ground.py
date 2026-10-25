#!/usr/bin/env python3
"""Drive the docs/PRODUCT.md demo against a running KIN server, through its HTTP API and LiveKit only.

Every call is one-to-one. The script creates Mei (zh), Arjun (en, phone), Priya (en) and Paatti (ta), plants call 1,
Arjun's own facts and Paatti's two Ravis with the dev routes, sends the "started bouldering" SMS, has Arjun tell Priya
on a call, then runs call 2 (Arjun and Mei) and the Paatti call. For each call it joins both people as LiveKit
participants, types the lines with POST /api/calls/{id}/text, and prints what each listener received next to what they
should get.

After creating the users it prints a kin://signin link per person. Open one on a phone (debug build) to sign in as that
person. --plant-only stops after the planted history and the Priya call, so the phones play call 2 and the Paatti call
themselves (the driver then holds no LiveKit identity a phone uses).

Needs: the backend started with DEV_ENDPOINTS=1 and a MODEL_API_KEY (MT and the SMS parse are live), `livekit-server
--dev`, and a fresh database (the users are created here; a second run hits "phone already linked").

    cd backend && .venv/bin/python ../scripts/demo_common_ground.py [--next-day] [--wait 10]
    cd backend && KIN_BASE=http://<laptop LAN IP>:8000 .venv/bin/python ../scripts/demo_common_ground.py --plant-only
    cd backend && .venv/bin/python ../scripts/demo_common_ground.py --reset-clock

Env: KIN_BASE (default http://localhost:8000), KIN_KEY (the KIN API key, if the server is locked).
Exits non-zero on any HTTP error.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from urllib.parse import urlencode, urlsplit

import httpx

BASE = os.environ.get("KIN_BASE", "http://localhost:8000").rstrip("/")
KEY = os.environ.get("KIN_KEY", "")
ARJUN_PHONE = "+15125550101"
JOIN_RETRY_S, JOIN_TRIES = 0.25, 60  # /text answers 409 until the KIN agent has joined that participant
MEI_LINE = "我和林去攀岩了"  # "I went climbing with Lin."
PAATTI_LINE = "உன் நண்பர்கள் எல்லாம் எப்படி இருக்காங்க?"  # "How are all your friends?"
ARJUN_TO_PAATTI = "I went hiking with Mei when she visited."
ARJUN_TO_PRIYA = "I started bouldering last week."
# "Ravi mama came yesterday; Ravi periyappa is coming next week." Two uncles named Ravi, told apart by the kin word.
PAATTI_RAVIS = "ரவி மாமா நேத்து வந்தாரு, ரவி பெரியப்பா அடுத்த வாரம் வர்றாரு."
LOOPBACK = ("localhost", "127.0.0.1", "::1")


def signin_link(token: str, base: str = BASE, key: str = KEY) -> str:
    """kin://signin for the iOS debug build. `server` only when a phone could reach it (not loopback)."""
    q = {"token": token}
    if urlsplit(base).hostname not in LOOPBACK:
        q["server"] = base
    if key:
        q["key"] = key
    return "kin://signin?" + urlencode(q)


class HttpError(SystemExit):
    pass


def _fact(subject: str, predicate: str, text: str, refs: list[str], keys: list[list[str]], src: str = "") -> dict:
    return {"subject": subject, "predicate": predicate, "text_en": text, "text_src": src, "keys": keys, "refs": refs,
            "lines": [0], "sensitive_kind": "", "same_as": None, "contradicts": None, "storyline": None}


class Leg:
    """One person in a LiveKit room, collecting KIN's data messages (topic 'kin') addressed to them."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.msgs: list[dict] = []
        self.room = None

    async def connect(self, join: dict) -> "Leg":
        from livekit import rtc  # backend extra `livekit` (rtc SDK 1.1.21); lazy so --reset-clock needs nothing

        self.room = rtc.Room()

        def got(packet: "rtc.DataPacket") -> None:
            if packet.topic != "kin":
                return
            try:
                self.msgs.append(json.loads(packet.data))
            except ValueError as e:
                print(f"  ! {self.name}: undecodable message: {e}", file=sys.stderr)

        self.room.on("data_received", got)
        await self.room.connect(join["url"], join["token"], rtc.RoomOptions(auto_subscribe=False))
        return self

    def take(self) -> list[dict]:
        out, self.msgs = self.msgs, []
        return out

    async def hang_up(self) -> None:
        if self.room is not None:
            await self.room.disconnect()


class Demo:
    def __init__(self, http: httpx.AsyncClient, wait_s: float) -> None:
        self.http = http
        self.wait_s = wait_s
        self.token: dict[str, str] = {}
        self.slug: dict[str, str] = {}

    async def post(self, path: str, body: dict, who: str | None = None, ok409: bool = False) -> httpx.Response:
        headers = {"X-KIN-User": self.token[who]} if who else {}
        try:
            r = await self.http.post(path, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise HttpError(f"POST {path}: {type(e).__name__}: {e} (is the backend running at {BASE}?)") from e
        if r.status_code == 404 and path.startswith("/api/dev/"):
            raise HttpError(f"POST {path}: 404. Start the backend with DEV_ENDPOINTS=1 (dev routes are off by default); "
                            "a locked server answers them only on loopback, so go through an ssh tunnel.")
        if r.status_code >= 400 and not (ok409 and r.status_code == 409):
            raise HttpError(f"POST {path}: HTTP {r.status_code}: {r.text[:400]}")
        return r

    async def json(self, path: str, body: dict, who: str | None = None) -> dict:
        return (await self.post(path, body, who)).json()

    async def clock(self, days: float) -> None:
        out = await self.json("/api/dev/clock", {"offset_days": days})
        print(f"\n== clock {days:+g} days: server now {out['now']}")

    # ---- setup -------------------------------------------------------------------------------------------------------
    async def users(self) -> None:
        for name, lang, phone in [("Mei", "zh", None), ("Arjun", "en", ARJUN_PHONE), ("Priya", "en", None),
                                  ("Paatti", "ta", None)]:
            out = await self.json("/api/users", {"name": name, "lang": lang, "phone": phone})
            self.token[name], self.slug[name] = out["token"], out["person"]
            print(f"user {name} ({lang}) -> {out['person']}")

    def print_signin_links(self) -> None:
        print("\nSign a phone in as one of these people (debug build: open the link, or paste it under Sign up > Server):")
        for name, tok in self.token.items():
            print(f"  {name}: {signin_link(tok)}")

    async def apply(self, speaker: str, audience: list[str], update: dict) -> dict:
        body = {"speaker": self.slug[speaker], "audience": [self.slug[a] for a in audience], "update": update}
        out = await self.json("/api/dev/apply", body)
        print(f"apply by {speaker} heard by {audience or 'nobody'}: facts {out['facts']}")
        return out

    async def plant_call_1(self) -> None:
        """Call 1 (September): Mei tells Arjun about her climbing friend Lin."""
        lin = {"ref": "lin", "name": "Lin", "native": "林", "forms": ["林", "Lin", "Lynn"], "kind": "person",
               "existing_id": None}
        await self.apply("Mei", ["Arjun"], {
            "entities": [lin],
            "ties": [{"a": "speaker", "b": "lin", "kind": "friend", "context": "from the Fudan climbing wall"}],
            "facts": [_fact("speaker", "tie", "Lin is Mei's friend from the Fudan climbing wall", ["lin"], [],
                            "林是我在复旦攀岩墙认识的朋友")]})

    async def plant_arjun(self) -> None:
        """Arjun's own facts: who Mei is to him (nobody else heard it) and the hiking trip (Mei was there)."""
        mei = self.slug["Mei"]
        await self.apply("Arjun", [], {
            "entities": [],
            "ties": [{"a": "speaker", "b": mei, "kind": "friend", "context": "from high school, now in Shanghai"}],
            "facts": [_fact("speaker", "tie", "Mei is Arjun's friend from high school, now in Shanghai", [mei], [])]})
        await self.apply("Arjun", ["Mei"], {"entities": [], "ties": [], "facts": [_fact(
            "speaker", "did", "went hiking with Mei when she visited", [mei],
            [["hiking", "hike", "hiked", "மலையேற்றம்"], ["friends", "friend", "நண்பர்கள்", "நண்பர்", "朋友"]])]})
        out = await self.json("/api/world/place", {"person": self.slug["Paatti"], "owner": self.slug["Arjun"],
                                                   "relation": "mother.mother"}, "Arjun")
        print(f"placed Paatti for Arjun: {out['render']}")

    async def plant_ravis(self) -> None:
        """Paatti's two Ravis (demo beat 5): told to Arjun, then placed by kin path so each is named for who he is.
        Placed by slug: placing the second "Ravi" by name would attach the first one at a second kin path."""
        ravis = [("ravi_mama", ["ரவி மாமா", "Ravi mama"], "Ravi mama lives in Chennai", "ரவி மாமா சென்னையில இருக்கான்",
                  "mother.younger_brother"),
                 ("ravi_periyappa", ["ரவி பெரியப்பா", "Ravi periyappa"], "Ravi periyappa lives in Madurai",
                  "ரவி பெரியப்பா மதுரையில இருக்காரு", "father.elder_brother")]
        out = await self.apply("Paatti", ["Arjun"], {
            "entities": [{"ref": ref, "name": "Ravi", "native": "ரவி", "forms": forms, "kind": "person",
                          "existing_id": None} for ref, forms, *_ in ravis],
            "ties": [],
            "facts": [_fact(ref, "lives_in", text, [], [], src) for ref, _f, text, src, _r in ravis]})
        slug = {e["ref"]: e["slug"] for e in out["entities"]}
        for ref, _f, _t, _s, relation in ravis:
            placed = await self.json("/api/world/place", {"person": slug[ref], "owner": self.slug["Arjun"],
                                                          "relation": relation}, "Arjun")
            print(f"placed {ref} for Arjun: {placed['render']}")

    async def sms(self) -> None:
        out = await self.json("/api/dev/sms", {"from": ARJUN_PHONE, "body": "started bouldering"})
        print(f"SMS from Arjun -> reply {out['reply']!r}, facts {[f['text'] for f in out.get('facts', [])]}")

    # ---- calls -------------------------------------------------------------------------------------------------------
    async def call(self, a: str, b: str) -> tuple[int, dict[str, Leg]]:
        ja = await self.json("/api/rtc/join", {}, a)
        jb = await self.json("/api/rtc/join", {"call_id": ja["call_id"], "invite": ja["invite"]}, b)
        legs = {a: await Leg(a).connect(ja), b: await Leg(b).connect(jb)}
        print(f"\n-- call {ja['call_id']}: {a} and {b}")
        return ja["call_id"], legs

    async def say(self, call_id: int, legs: dict[str, Leg], who: str, text: str, expect: dict[str, str]) -> None:
        for _ in range(JOIN_TRIES):
            r = await self.post(f"/api/calls/{call_id}/text", {"text": text}, who, ok409=True)
            if r.status_code != 409:
                break
            await asyncio.sleep(JOIN_RETRY_S)
        else:
            raise HttpError(f"call {call_id}: {who} never joined on the server side (409 {r.text[:200]})")
        print(f"{who} says: {text}")
        await asyncio.sleep(self.wait_s)  # MT, bridges and localization land within a few seconds
        for name, leg in legs.items():
            if name != who:
                show(name, leg.take(), expect.get(name, "nothing"))
        if expect.get(who):
            show(who, legs[who].take(), expect[who])
        else:
            legs[who].take()

    async def hang_up(self, legs: dict[str, Leg]) -> None:
        for leg in legs.values():
            await leg.hang_up()


def show(name: str, msgs: list[dict], expect: str) -> None:
    print(f"  {name} expects: {expect}")
    for m in msgs:
        t = m.get("type")
        if t == "transcript" and m.get("translation"):
            print(f"    caption: {m['translation']}")
        elif t == "glance":
            for it in m.get("items", []):
                print(f"    card [{it.get('kind')}] {it.get('title', '')}: {it.get('body', '')}")
        elif t == "glance_retract":
            print(f"    retract {m.get('keys')}")
        elif t == "glance_update":
            print(f"    localized {m.get('key')}: {m.get('body')}")
        elif t == "error":
            print(f"    error ({m.get('stage')}): {m.get('message')}")


async def run(args: argparse.Namespace) -> None:
    headers = {"X-KIN-Key": KEY} if KEY else {}
    async with httpx.AsyncClient(base_url=BASE, headers=headers, timeout=30.0) as http:
        d = Demo(http, args.wait)
        if args.reset_clock:
            await d.clock(0)
            return
        await d.clock(-42)
        await d.users()
        await d.plant_call_1()
        await d.plant_arjun()

        await d.clock(-3)
        await d.plant_ravis()
        await d.sms()
        cid, legs = await d.call("Arjun", "Priya")
        await d.say(cid, legs, "Arjun", ARJUN_TO_PRIYA, {"Priya": "the caption only (no cards)"})
        await d.hang_up(legs)

        await d.clock(0)
        d.print_signin_links()
        if args.plant_only:
            print("\nPlanted. The phones play call 2 and the Paatti call; the driver holds no LiveKit seat.")
            return
        cid, legs = await d.call("Arjun", "Mei")
        await d.say(cid, legs, "Mei", MEI_LINE, {
            "Arjun": "Lin card (reminder: Mei's friend from the Fudan climbing wall) and the private bridge "
                     "'You haven't told Mei: started bouldering'"})
        await d.hang_up(legs)

        if args.next_day:
            await d.clock(1)
            cid, legs = await d.call("Arjun", "Mei")
            await d.say(cid, legs, "Mei", MEI_LINE, {"Arjun": "the caption only: no card, no bridge"})
            await d.hang_up(legs)

        await d.clock(2)  # past the 90 s bridge gap from call 2
        cid, legs = await d.call("Arjun", "Paatti")
        await d.say(cid, legs, "Paatti", PAATTI_LINE, {
            "Arjun": "the caption and the bridge 'You haven't told Paatti: went hiking with Mei when she visited'"})
        await d.say(cid, legs, "Arjun", ARJUN_TO_PAATTI, {
            "Paatti": "a Tamil caption and a card for Mei (your grandson Arjun's friend, from high school, now in "
                      "Shanghai), localized to Tamil",
            "Arjun": "the hiking bridge retracted (he just told her)"})
        await d.say(cid, legs, "Paatti", PAATTI_RAVIS, {
            "Arjun": "a caption that names each Ravi for who he is: Mom's younger brother, then Dad's elder brother"})
        await d.hang_up(legs)
        await d.clock(0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--reset-clock", action="store_true", help="set the server clock offset back to 0 and exit")
    ap.add_argument("--plant-only", action="store_true",
                    help="plant the history and the Priya call, print sign-in links, and exit (phones play the rest)")
    ap.add_argument("--next-day", action="store_true", help="after call 2, move the clock +1 day and repeat Mei's line")
    ap.add_argument("--wait", type=float, default=10.0, help="seconds to wait for cards after each line")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()

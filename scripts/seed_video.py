"""Seed two months of history for the demo video: Karthik (English) with Vikshar (English) and with Nithin (Tamil).

Against a fresh server started with DEV_ENDPOINTS=1. Same planting path as seed_karthik_nithin.py (dev clock +
/api/dev/apply + /api/dev/sms), so every fact goes through the same validation and visibility rules as a real call
or text. The Karthik and Nithin history is identical to seed_karthik_nithin.py; this adds Vikshar on top:

    cd backend && KIN_BASE='http://[::1]:8000' .venv/bin/python ../scripts/seed_video.py

Rename the English friend with --english-name. Prints all three sign-in tokens (see the demo video script).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_common_ground import BASE, KEY, Demo, HttpError, _fact  # noqa: E402

KARTHIK_PHONE = "+15125550142"
NITHIN_PHONE = "+15125550177"
FRIEND_PHONE = "+15125550163"
ADOBE_KEYS = [["adobe", "அடோப்"], ["internship", "intern", "interview", "இன்டர்ன்ஷிப்", "இன்டர்வியூ"]]
APARTMENT_KEYS = [["apartment", "apartments", "lease"], ["off campus", "near campus", "move in", "moving"]]


def story(fact: dict, title: str, state: str, existing: int | None = None) -> dict:
    return {**fact, "storyline": {"existing_id": existing, "title": title, "state_label": state, "resolved": False}}


async def storyline_id(http: httpx.AsyncClient, token: str, needle: str) -> int | None:
    world = (await http.get("/api/world", headers={"X-KIN-User": token})).json()
    return next((s["id"] for s in world.get("storylines", []) if needle in s.get("title", "").lower()), None)


async def seed(args: argparse.Namespace) -> dict:
    friend = args.english_name
    headers = {"X-KIN-Key": KEY} if KEY else {}
    async with httpx.AsyncClient(base_url=BASE, timeout=90, headers=headers) as http:
        d = Demo(http, wait_s=0)
        for name, lang, phone in [("Karthik", "en", KARTHIK_PHONE), (friend, "en", FRIEND_PHONE),
                                  ("Nithin", "ta", NITHIN_PHONE)]:
            out = await d.json("/api/users", {"name": name, "lang": lang, "phone": phone})
            d.token[name], d.slug[name] = out["token"], out["person"]
            print(f"user {name} ({lang}) -> {out['person']}")
        k, v, n = d.slug["Karthik"], d.slug[friend], d.slug["Nithin"]

        # Connected, so Karthik can ring either of them without a link.
        for other, slug in [(friend, v), ("Nithin", n)]:
            await d.json("/api/connect", {"slug": slug}, "Karthik")
            await d.json(f"/api/connect/{k}/accept", {}, other)
            print(f"connected Karthik <-> {other}")

        # ~60 days ago: who they are to each other, and Karthik's friend Mei (his own fact, heard by nobody yet).
        await d.clock(-60)
        mei = {"ref": "mei", "name": "Mei", "native": "", "forms": ["Mei", "மெய்"], "kind": "person", "existing_id": None}
        await d.apply("Karthik", [], {"entities": [mei], "ties": [
            {"a": "speaker", "b": n, "kind": "friend", "context": "from freshman year"},
            {"a": "speaker", "b": v, "kind": "friend", "context": "from high school"},
            {"a": "speaker", "b": "mei", "kind": "friend", "context": "from high school, now in Shanghai"}], "facts": [
            _fact("speaker", "tie", "Nithin is Karthik's friend from freshman year", [n], []),
            _fact("speaker", "tie", f"{friend} is Karthik's friend from high school, now at another college", [v], []),
            _fact("speaker", "tie", "Mei is Karthik's friend from high school, now in Shanghai", ["mei"], [])]})
        await d.apply("Nithin", [], {"entities": [], "ties": [
            {"a": "speaker", "b": k, "kind": "friend", "context": "from freshman year"}], "facts": [
            _fact("speaker", "tie", "Karthik is Nithin's friend from freshman year", [k], [],
                  "கார்த்திக் என் freshman year ஃப்ரெண்ட்")]})
        await d.apply(friend, [], {"entities": [], "ties": [
            {"a": "speaker", "b": k, "kind": "friend", "context": "from high school"}], "facts": [
            _fact("speaker", "tie", f"Karthik is {friend}'s friend from high school", [k], [])]})

        # Call, ~58 days ago: the English friend's new friend Maya from the robotics team.
        await d.clock(-58)
        maya = {"ref": "maya", "name": "Maya", "native": "", "forms": ["Maya"], "kind": "person", "existing_id": None}
        await d.apply(friend, ["Karthik"], {"entities": [maya], "ties": [
            {"a": "speaker", "b": "maya", "kind": "friend", "context": "from the robotics team"}], "facts": [
            _fact("speaker", "tie", f"Maya is {friend}'s friend from the robotics team", ["maya"], [])]})

        # Call, ~56 days ago: Nithin's new climbing friend Rohan.
        await d.clock(-56)
        rohan = {"ref": "rohan", "name": "Rohan", "native": "ரோஹன்", "forms": ["ரோஹன்", "Rohan"], "kind": "person",
                 "existing_id": None}
        await d.apply("Nithin", ["Karthik"], {"entities": [rohan], "ties": [
            {"a": "speaker", "b": "rohan", "kind": "friend", "context": "from the climbing gym"}], "facts": [
            _fact("speaker", "tie", "Rohan is Nithin's friend from the climbing gym", ["rohan"], [],
                  "ரோஹன்னு climbing gym-ல ஒரு புது ஃப்ரெண்ட் கிடைச்சான்")]})

        # Call, ~50 days ago: Nithin's two uncles, both named Ravi.
        await d.clock(-50)
        ravis = [("ravi_mama", ["ரவி மாமா", "Ravi mama"], "Ravi mama is Nithin's mom's younger brother; he lives in Chennai",
                  "ரவி மாமா அம்மாவோட தம்பி, சென்னையில இருக்கார்", "mother.younger_brother"),
                 ("ravi_periyappa", ["ரவி பெரியப்பா", "Ravi periyappa"],
                  "Ravi periyappa is Nithin's dad's elder brother; he lives in Madurai",
                  "ரவி பெரியப்பா அப்பாவோட அண்ணன், மதுரையில இருக்கார்", "father.elder_brother")]
        out = await d.apply("Nithin", ["Karthik"], {
            "entities": [{"ref": ref, "name": "Ravi", "native": "ரவி", "forms": forms, "kind": "person",
                          "existing_id": None} for ref, forms, *_ in ravis],
            "ties": [], "facts": [_fact(ref, "relation", text, [], [], src) for ref, _f, text, src, _r in ravis]})
        slug = {e["ref"]: e["slug"] for e in out.get("entities", [])}
        for ref, _f, _t, _s, relation in ravis:
            if ref in slug:
                try:
                    placed = await d.json("/api/world/place", {"person": slug[ref], "owner": n, "relation": relation},
                                          "Nithin")
                    print(f"placed {ref} for Nithin: {placed.get('render')}")
                except HttpError as e:  # the facts above already say who each Ravi is
                    print(f"  (placing {ref} skipped: {e})")

        # Call, ~45 days ago: the English friend starts an apartment hunt.
        await d.clock(-45)
        await d.apply(friend, ["Karthik"], {"entities": [], "ties": [], "facts": [story(
            _fact("speaker", "did", "started looking for an apartment off campus", [], APARTMENT_KEYS),
            "apartment hunt", "looking")]})

        # Call, ~42 days ago: Nithin applies for the Adobe internship.
        await d.clock(-42)
        await d.apply("Nithin", ["Karthik"], {"entities": [], "ties": [], "facts": [story(
            _fact("speaker", "did", "applied for the Adobe internship", [], ADOBE_KEYS,
                  "Adobe internship-க்கு apply பண்ணேன்"), "Adobe internship", "applied")]})

        # Call, ~31 days ago: the apartment hunt moves on.
        await d.clock(-31)
        sid = await storyline_id(http, d.token[friend], "apartment")
        await d.apply(friend, ["Karthik"], {"entities": [], "ties": [], "facts": [story(
            _fact("speaker", "did", "toured two apartments near campus", [], APARTMENT_KEYS),
            "apartment hunt", "toured two places", sid)]})

        # Call, ~28 days ago: Nithin's final-round interview.
        await d.clock(-28)
        sid = await storyline_id(http, d.token["Nithin"], "adobe")
        await d.apply("Nithin", ["Karthik"], {"entities": [], "ties": [], "facts": [story(
            _fact("speaker", "did", "had the final-round interview for the Adobe internship", [], ADOBE_KEYS,
                  "Adobe final round interview முடிஞ்சது"), "Adobe internship", "final round", sid)]})

        # ~14 days ago: Karthik texts KIN his news. Private; neither friend has heard it.
        await d.clock(-14)
        out = await d.json("/api/dev/sms", {"from": KARTHIK_PHONE, "body": "started bouldering at the campus gym"})
        print(f"Karthik texted KIN -> {out['reply']!r}")

        await d.clock(0)
        tokens = {name: d.token[name] for name in ("Karthik", friend, "Nithin")}
        print("\nSIGN-IN TOKENS " + json.dumps(tokens))
        return tokens


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--english-name", default="Vikshar", help="name of the English-speaking friend (default Vikshar)")
    try:
        asyncio.run(seed(ap.parse_args()))
    except HttpError as e:
        sys.exit(f"seed failed: {e}")


if __name__ == "__main__":
    main()

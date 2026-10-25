"""Seed two months of lived-in history between Karthik (English) and Nithin (Tamil) for the live demo.

Against a fresh server started with DEV_ENDPOINTS=1. Uses the demo driver's planting helpers (dev clock + /api/dev/apply
+ /api/dev/sms), so every fact goes through the same validation and visibility rules as a real call or text. Each
planted line is what the person said on an earlier call (Tamil for Nithin, with the English KIN stored):

    cd backend && KIN_BASE='http://[::1]:8000' .venv/bin/python ../scripts/seed_karthik_nithin.py

Prints both sign-in tokens; build each phone with its token baked in (see docs/DEMO_SCRIPT.md).
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
ADOBE_KEYS = [["adobe", "அடோப்"], ["internship", "intern", "interview", "இன்டர்ன்ஷிப்", "இன்டர்வியூ"]]


def story(fact: dict, title: str, state: str, existing: int | None = None) -> dict:
    return {**fact, "storyline": {"existing_id": existing, "title": title, "state_label": state, "resolved": False}}


async def seed(args: argparse.Namespace) -> dict:
    headers = {"X-KIN-Key": KEY} if KEY else {}
    async with httpx.AsyncClient(base_url=BASE, timeout=90, headers=headers) as http:
        d = Demo(http, wait_s=0)
        for name, lang, phone in [("Karthik", "en", KARTHIK_PHONE), ("Nithin", "ta", NITHIN_PHONE)]:
            out = await d.json("/api/users", {"name": name, "lang": lang, "phone": phone})
            d.token[name], d.slug[name] = out["token"], out["person"]
            print(f"user {name} ({lang}) -> {out['person']}")
        k, n = d.slug["Karthik"], d.slug["Nithin"]

        # Connected, so either can ring the other without a link.
        await d.json("/api/connect", {"slug": n}, "Karthik")
        await d.json(f"/api/connect/{k}/accept", {}, "Nithin")
        print("connected Karthik <-> Nithin")

        # Who they are to each other, and Karthik's friend Mei (his own facts, heard by nobody yet).
        await d.clock(-60)
        mei = {"ref": "mei", "name": "Mei", "native": "", "forms": ["Mei", "மெய்"], "kind": "person", "existing_id": None}
        await d.apply("Karthik", [], {"entities": [mei], "ties": [
            {"a": "speaker", "b": n, "kind": "friend", "context": "from freshman year"},
            {"a": "speaker", "b": "mei", "kind": "friend", "context": "from high school, now in Shanghai"}], "facts": [
            _fact("speaker", "tie", "Nithin is Karthik's friend from freshman year", [n], []),
            _fact("speaker", "tie", "Mei is Karthik's friend from high school, now in Shanghai", ["mei"], [])]})
        await d.apply("Nithin", [], {"entities": [], "ties": [
            {"a": "speaker", "b": k, "kind": "friend", "context": "from freshman year"}], "facts": [
            _fact("speaker", "tie", "Karthik is Nithin's friend from freshman year", [k], [],
                  "கார்த்திக் என் freshman year ஃப்ரெண்ட்")]})

        # Call, ~8 weeks ago: Nithin's new climbing friend Rohan.
        await d.clock(-56)
        rohan = {"ref": "rohan", "name": "Rohan", "native": "ரோஹன்", "forms": ["ரோஹன்", "Rohan"], "kind": "person",
                 "existing_id": None}
        await d.apply("Nithin", ["Karthik"], {"entities": [rohan], "ties": [
            {"a": "speaker", "b": "rohan", "kind": "friend", "context": "from the climbing gym"}], "facts": [
            _fact("speaker", "tie", "Rohan is Nithin's friend from the climbing gym", ["rohan"], [],
                  "ரோஹன்னு climbing gym-ல ஒரு புது ஃப்ரெண்ட் கிடைச்சான்")]})

        # Call, ~7 weeks ago: Nithin's two uncles, both named Ravi.
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

        # Calls, ~6 and ~4 weeks ago: Nithin's Adobe internship thread.
        await d.clock(-42)
        await d.apply("Nithin", ["Karthik"], {"entities": [], "ties": [], "facts": [story(
            _fact("speaker", "did", "applied for the Adobe internship", [], ADOBE_KEYS,
                  "Adobe internship-க்கு apply பண்ணேன்"), "Adobe internship", "applied")]})
        await d.clock(-28)
        world = (await http.get("/api/world", headers={"X-KIN-User": d.token["Nithin"]})).json()
        sid = next((s["id"] for s in world.get("storylines", []) if "Adobe" in s.get("title", "")), None)
        await d.apply("Nithin", ["Karthik"], {"entities": [], "ties": [], "facts": [story(
            _fact("speaker", "did", "had the final-round interview for the Adobe internship", [], ADOBE_KEYS,
                  "Adobe final round interview முடிஞ்சது"), "Adobe internship", "final round", sid)]})

        # ~2 weeks ago: Karthik texts KIN his news. Private; Nithin has not heard it.
        await d.clock(-14)
        out = await d.json("/api/dev/sms", {"from": KARTHIK_PHONE, "body": "started bouldering at the campus gym"})
        print(f"Karthik texted KIN -> {out['reply']!r}")

        await d.clock(0)
        tokens = {"Karthik": d.token["Karthik"], "Nithin": d.token["Nithin"]}
        print("\nSIGN-IN TOKENS " + json.dumps(tokens))
        return tokens


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    try:
        asyncio.run(seed(ap.parse_args()))
    except HttpError as e:
        sys.exit(f"seed failed: {e}")


if __name__ == "__main__":
    main()

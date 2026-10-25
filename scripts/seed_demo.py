"""Seed the demo world: Karthik (CMU) and Nithin (UT Turing Scholar), high school friends, both in English.

Only context is planted, never the demo itself (docs/DEMO_SCRIPT.md says what to talk about). Two parts share it:
- Part 1, friends: Nithin's world (climbing friend Rohan, the Meta application) heard by Karthik ~7 weeks ago,
  Karthik's (project partner Priya) heard by Nithin, and news each has not told the other (Karthik's bouldering and
  HackTX trip).
- Part 2, grandmother: midway Nithin renames himself Grandma and switches to Tamil in Settings. The same account then
  carries her side: Karthik's two uncles named Ravi, her sister Saroja and cousin Meena's engagement (heard by
  Karthik), Karthik's roommate Mei (heard by her ~8 weeks ago), his hiking trip with Mei and her bhajan group (untold).
Part 2 names and topics stay out of Part 1 (mentioning Mei to Nithin would refresh what "Paatti" knows), and the Part 2
bridges only match Tamil friend words or music, so the English friends call does not use them up.

Against a fresh server started with DEV_ENDPOINTS=1:

    cd backend && KIN_BASE='http://[::1]:8000' .venv/bin/python ../scripts/seed_demo.py
    .venv/bin/python ../scripts/demo_snapshot.py save

--rehearse plays both calls with typed lines after seeding (for a throwaway server: it changes what KIN thinks they know).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_common_ground import BASE, KEY, Demo, HttpError, _fact, signin_link  # noqa: E402

KARTHIK_PHONE, NITHIN_PHONE = "+15125550142", "+15125550177"
TAMIL_FRIENDS = ["நண்பர்கள்", "நண்பர்", "ஃப்ரெண்ட்ஸ்"]  # Paatti asks in Tamil; Part 1 is English, so it never matches


def _person(ref: str, name: str, native: str = "") -> dict:
    forms = [name] + ([native] if native else [])
    return {"ref": ref, "name": name, "native": native, "forms": forms, "kind": "person", "existing_id": None}


def _story(fact: dict, title: str, state: str) -> dict:
    return {**fact, "storyline": {"existing_id": None, "title": title, "state_label": state, "resolved": False}}


def _tie(ref: str, context: str) -> dict:
    return {"a": "speaker", "b": ref, "kind": "friend", "context": context}


async def plant(d: Demo) -> None:
    for name, phone in [("Karthik", KARTHIK_PHONE), ("Nithin", NITHIN_PHONE)]:
        out = await d.json("/api/users", {"name": name, "lang": "en", "phone": phone})
        d.token[name], d.slug[name] = out["token"], out["person"]
    k, n = d.slug["Karthik"], d.slug["Nithin"]
    await d.json("/api/connect", {"slug": n}, "Karthik")
    await d.json(f"/api/connect/{k}/accept", {}, "Nithin")

    # ~2 months ago: who they are to each other, said on a call both heard.
    await d.clock(-60)
    await d.apply("Karthik", ["Nithin"], {"entities": [], "ties": [_tie(n, "from high school")], "facts": [
        _fact("speaker", "tie", "Nithin is Karthik's friend from high school", [n], []),
        _fact("speaker", "did", "studies computer science at Carnegie Mellon", [], [])]})
    await d.apply("Nithin", ["Karthik"], {"entities": [], "ties": [_tie(k, "from high school")], "facts": [
        _fact("speaker", "tie", "Karthik is Nithin's friend from high school", [k], []),
        _fact("speaker", "did", "is a Turing Scholar at UT Austin", [], [])]})

    # ~8 weeks ago: Karthik's roommate Mei (Part 2: "Paatti" gets the reminder in Tamil).
    await d.clock(-56)
    await d.apply("Karthik", ["Nithin"], {"entities": [_person("mei", "Mei", "மெய்")],
                                          "ties": [_tie("mei", "his roommate at CMU, from Shanghai")], "facts": [
        _fact("speaker", "tie", "Mei is Karthik's roommate at CMU, from Shanghai", ["mei"], [])]})

    # ~7 weeks ago: Karthik's project partner Priya (Part 1: Nithin's reminder).
    await d.clock(-52)
    await d.apply("Karthik", ["Nithin"], {"entities": [_person("priya", "Priya")],
                                          "ties": [_tie("priya", "his robotics project partner at CMU")], "facts": [
        _fact("speaker", "tie", "Priya is Karthik's robotics project partner at CMU", ["priya"], [])]})

    # ~7 weeks ago: Nithin's climbing friend Rohan and his Meta application (Part 1: Karthik's reminders),
    # and the two Ravis (Part 2: placed by kin path relative to Karthik, by the speaker, so Karthik only heard them).
    await d.clock(-50)
    await d.apply("Nithin", ["Karthik"], {"entities": [_person("rohan", "Rohan", "ரோஹன்")],
                                          "ties": [_tie("rohan", "from the climbing gym at UT")], "facts": [
        _fact("speaker", "tie", "Rohan is Nithin's friend from the climbing gym at UT", ["rohan"], [])]})
    await d.apply("Nithin", ["Karthik"], {"entities": [], "ties": [], "facts": [_story(_fact(
        "speaker", "did", "applied for the Meta internship", [],
        [["meta", "facebook"], ["internship", "intern", "interview", "superday", "offer"]]),
        "Meta internship", "applied")]})
    ravis = [("ravi_mama", "Ravi mama", "ரவி மாமா", "Ravi mama is Karthik's mom's younger brother; he lives in Chennai",
              "mother.younger_brother"),
             ("ravi_periyappa", "Ravi periyappa", "ரவி பெரியப்பா",
              "Ravi periyappa is Karthik's dad's elder brother; he lives in Madurai", "father.elder_brother")]
    out = await d.apply("Nithin", ["Karthik"], {
        "entities": [{"ref": ref, "name": "Ravi", "native": "ரவி", "forms": [native, latin], "kind": "person",
                      "existing_id": None} for ref, latin, native, *_ in ravis],
        "ties": [], "facts": [_fact(ref, "relation", text, [], []) for ref, _l, _n, text, _r in ravis]})
    slug = {e["ref"]: e["slug"] for e in out["entities"]}
    for ref, *_rest, relation in ravis:
        await d.json("/api/world/place", {"person": slug[ref], "owner": k, "relation": relation}, "Nithin")

    # ~6 weeks ago: Paatti's side (Part 2: Karthik's cards).
    await d.clock(-45)
    await d.apply("Nithin", ["Karthik"], {
        "entities": [_person("saroja", "Saroja", "சரோஜா"), _person("meena", "Meena", "மீனா")], "ties": [], "facts": [
            _fact("saroja", "relation", "Saroja is Grandma's younger sister; she lives in Coimbatore", [], []),
            _story(_fact("meena", "did", "Meena, Ravi mama's daughter, got engaged", [],
                         [["wedding", "marriage", "கல்யாணம்"], ["engaged", "engagement", "நிச்சயம்"]]),
                   "Meena's wedding", "engaged")]})

    # News nobody has heard yet (bridges).
    await d.clock(-21)
    await d.apply("Karthik", [], {"entities": [], "ties": [], "facts": [
        _fact("speaker", "did", "went hiking with Mei when she visited home", ["mei"],
              [["hiking", "hike", "hiked", "மலையேற்றம்"], TAMIL_FRIENDS])]})
    await d.apply("Nithin", [], {"entities": [], "ties": [], "facts": [
        _fact("speaker", "did", "joined a bhajan singing group at the temple", [],
              [["music", "singing", "sing", "song", "songs", "bhajan", "பாட்டு", "பஜன்"]])]})
    await d.clock(-14)
    await d.apply("Karthik", [], {"entities": [], "ties": [], "facts": [
        _fact("speaker", "did", "started bouldering at the CMU climbing wall", [],
              [["climbing", "climb", "climbed", "bouldering", "boulder"]])]})
    await d.clock(-7)
    await d.apply("Karthik", [], {"entities": [], "ties": [], "facts": [
        _fact("speaker", "did", "is flying to Austin for HackTX", [], [["hackathon", "hackathons", "hacktx"]])]})
    await d.clock(0)


async def rehearse(d: Demo) -> None:
    """Typed stand-ins for what people might say, to check the context fires; the real demo is unscripted."""
    cid, legs = await d.call("Karthik", "Nithin")
    try:
        await d.say(cid, legs, "Nithin", "Rohan and I hit the climbing gym again last weekend.",
                    {"Karthik": "Rohan reminder, bouldering bridge"})
        await d.say(cid, legs, "Karthik", "No way, I started bouldering at the CMU wall!", {"Karthik": "retract"})
        await d.say(cid, legs, "Nithin", "Oh, and I finally heard back from Meta.",
                    {"Karthik": "Meta storyline card"})
        await d.say(cid, legs, "Karthik", "Priya and I are entering our rover in a competition.",
                    {"Nithin": "Priya reminder"})
        await d.clock(0.01)  # past the 90 s gap between bridges
        await d.say(cid, legs, "Nithin", "Are you doing any hackathons this semester?", {"Karthik": "HackTX bridge"})
        await d.say(cid, legs, "Nithin", "Rohan and I hit the climbing gym again last weekend.", {"Karthik": "nothing"})
    finally:
        await d.hang_up(legs)
    await d.http.patch("/api/me", json={"name": "Grandma", "lang": "ta"}, headers={"X-KIN-User": d.token["Nithin"]})
    await d.clock(0.02)
    cid, legs = await d.call("Karthik", "Nithin")
    try:
        await d.say(cid, legs, "Nithin", "கண்ணா, சாப்டியா? ரொம்ப இளைச்சுட்ட மாதிரி இருக்கே.", {"Karthik": "care cards"})
        await d.say(cid, legs, "Nithin", "ரவி மாமா சென்னையில இருந்து வந்திருக்கார், ரவி பெரியப்பா மதுரையிலேயே இருக்கார்.",
                    {"Karthik": "two Ravi reminders"})
        await d.say(cid, legs, "Nithin", "உன் நண்பர்கள் எல்லாம் எப்படி இருக்காங்க?", {"Karthik": "hiking bridge"})
        await d.say(cid, legs, "Karthik", "I went hiking with Mei when she visited!",
                    {"Nithin": "Tamil Mei reminder", "Karthik": "retract"})
        await d.say(cid, legs, "Nithin", "மீனா கல்யாணம் ஜனவரில வச்சிருக்காங்க.", {"Karthik": "Meena storyline card"})
        await d.say(cid, legs, "Karthik", "Paatti, are you still singing at the temple?", {"Nithin": "bhajan bridge"})
    finally:
        await d.hang_up(legs)
    await d.http.patch("/api/me", json={"name": "Nithin", "lang": "en"}, headers={"X-KIN-User": d.token["Nithin"]})
    await d.clock(0)


async def run(args: argparse.Namespace) -> None:
    headers = {"X-KIN-Key": KEY} if KEY else {}
    async with httpx.AsyncClient(base_url=BASE, timeout=90, headers=headers) as http:
        d = Demo(http, wait_s=args.wait)
        await plant(d)
        for name in ("Karthik", "Nithin"):
            print(f"SIGNIN {name} {d.token[name]} {signin_link(d.token[name])}")
        if args.rehearse:
            await rehearse(d)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rehearse", action="store_true", help="after seeding, play both calls with typed lines")
    ap.add_argument("--wait", type=float, default=10.0, help="seconds to wait for cards after each line")
    try:
        asyncio.run(run(ap.parse_args()))
    except HttpError as e:
        sys.exit(f"seed failed: {e}")


if __name__ == "__main__":
    main()

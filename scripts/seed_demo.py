"""Seed one demo world (docs/DEMO_SCRIPT.md). Context only; the demo itself is acted out, never scripted here.

--part 1: Karthik (CMU) and Nithin (UT Turing Scholar), high school friends, both English. Nithin's climbing friend
  Rohan and Meta application (heard by Karthik ~7 weeks ago), Karthik's project partner Priya (heard by Nithin), and
  Karthik's untold news: bouldering, and flying to Austin for HackTX.
--part 2: Karthik and his grandmother (Mom's mom, Tamil). Her side heard by Karthik ~7 weeks ago: his two uncles named
  Ravi, her sister Saroja, cousin Meena's engagement. His side heard by her ~8 weeks ago: his roommate Mei. Untold:
  his hiking trip with Mei, her bhajan group.

Both parts create Karthik as user 1 and the second phone as user 2, so the Settings reset (POST /api/dev/reset) can
swap worlds with the same sign-ins. Against a fresh server started with DEV_ENDPOINTS=1:

    cd backend && KIN_BASE='http://[::1]:8000' .venv/bin/python ../scripts/seed_demo.py --part 1
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_common_ground import BASE, KEY, Demo, HttpError, _fact, signin_link  # noqa: E402

KARTHIK_PHONE, PHONE_B = "+15125550142", "+15125550177"
TAMIL_FRIENDS = ["நண்பர்கள்", "நண்பர்", "ஃப்ரெண்ட்ஸ்", "friends", "friend"]


def _person(ref: str, name: str, native: str = "") -> dict:
    forms = [name] + ([native] if native else [])
    return {"ref": ref, "name": name, "native": native, "forms": forms, "kind": "person", "existing_id": None}


def _story(fact: dict, title: str, state: str) -> dict:
    return {**fact, "storyline": {"existing_id": None, "title": title, "state_label": state, "resolved": False}}


def _tie(ref: str, context: str) -> dict:
    return {"a": "speaker", "b": ref, "kind": "friend", "context": context}


async def users(d: Demo, b: str, b_lang: str) -> tuple[str, str]:
    for name, lang, phone in [("Karthik", "en", KARTHIK_PHONE), (b, b_lang, PHONE_B)]:
        out = await d.json("/api/users", {"name": name, "lang": lang, "phone": phone})
        d.token[name], d.slug[name] = out["token"], out["person"]
    k, o = d.slug["Karthik"], d.slug[b]
    await d.json("/api/connect", {"slug": o}, "Karthik")
    await d.json(f"/api/connect/{k}/accept", {}, b)
    return k, o


async def part1(d: Demo) -> None:
    k, n = await users(d, "Nithin", "en")
    await d.clock(-60)
    await d.apply("Karthik", ["Nithin"], {"entities": [], "ties": [_tie(n, "from high school")], "facts": [
        _fact("speaker", "tie", "Nithin is Karthik's friend from high school", [n], []),
        _fact("speaker", "did", "studies computer science at Carnegie Mellon", [], [])]})
    await d.apply("Nithin", ["Karthik"], {"entities": [], "ties": [_tie(k, "from high school")], "facts": [
        _fact("speaker", "tie", "Karthik is Nithin's friend from high school", [k], []),
        _fact("speaker", "did", "is a Turing Scholar at UT Austin", [], [])]})

    await d.clock(-52)
    await d.apply("Karthik", ["Nithin"], {"entities": [_person("priya", "Priya")],
                                          "ties": [_tie("priya", "his robotics project partner at CMU")], "facts": [
        _fact("speaker", "tie", "Priya is Karthik's robotics project partner at CMU", ["priya"], [])]})

    await d.clock(-50)
    await d.apply("Nithin", ["Karthik"], {"entities": [_person("rohan", "Rohan")],
                                          "ties": [_tie("rohan", "from the climbing gym at UT")], "facts": [
        _fact("speaker", "tie", "Rohan is Nithin's friend from the climbing gym at UT", ["rohan"], [])]})
    await d.apply("Nithin", ["Karthik"], {"entities": [], "ties": [], "facts": [_story(_fact(
        "speaker", "did", "applied for the Meta internship", [],
        [["meta", "facebook"], ["internship", "intern", "interview", "offer"]]), "Meta internship", "applied")]})

    await d.clock(-14)
    await d.apply("Karthik", [], {"entities": [], "ties": [], "facts": [
        _fact("speaker", "did", "started bouldering at the CMU climbing wall", [],
              [["climbing", "climb", "climbed", "bouldering", "boulder"]])]})
    await d.clock(-7)
    await d.apply("Karthik", [], {"entities": [], "ties": [], "facts": [
        _fact("speaker", "did", "is flying to Austin for HackTX", [], [["hackathon", "hackathons", "hacktx"]])]})
    await d.clock(0)


async def part2(d: Demo) -> None:
    k, g = await users(d, "Grandma", "ta")
    await d.clock(-60)
    placed = await d.json("/api/world/place", {"person": g, "owner": k, "relation": "mother.mother"}, "Karthik")
    print(f"placed Grandma for Karthik: {placed['render']}")

    # ~8 weeks ago: Karthik told her about his roommate Mei (her reminder now, in Tamil).
    await d.clock(-56)
    await d.apply("Karthik", ["Grandma"], {"entities": [_person("mei", "Mei", "மெய்")],
                                           "ties": [_tie("mei", "his roommate at CMU, from Shanghai")], "facts": [
        _fact("speaker", "tie", "Mei is Karthik's roommate at CMU, from Shanghai", ["mei"], [])]})

    # ~7 weeks ago: his two uncles named Ravi, placed by kin path by her, so Karthik only heard them (his reminders).
    await d.clock(-50)
    ravis = [("ravi_mama", "Ravi mama", "ரவி மாமா", "Ravi mama is Karthik's mom's younger brother; he lives in Chennai",
              "mother.younger_brother"),
             ("ravi_periyappa", "Ravi periyappa", "ரவி பெரியப்பா",
              "Ravi periyappa is Karthik's dad's elder brother; he lives in Madurai", "father.elder_brother")]
    out = await d.apply("Grandma", ["Karthik"], {
        "entities": [{"ref": ref, "name": "Ravi", "native": "ரவி", "forms": [native, latin], "kind": "person",
                      "existing_id": None} for ref, latin, native, *_ in ravis],
        "ties": [], "facts": [_fact(ref, "relation", text, [], []) for ref, _l, _n, text, _r in ravis]})
    slug = {e["ref"]: e["slug"] for e in out["entities"]}
    for ref, *_rest, relation in ravis:
        await d.json("/api/world/place", {"person": slug[ref], "owner": k, "relation": relation}, "Grandma")

    await d.clock(-45)
    await d.apply("Grandma", ["Karthik"], {
        "entities": [_person("saroja", "Saroja", "சரோஜா"), _person("meena", "Meena", "மீனா")], "ties": [], "facts": [
            _fact("saroja", "relation", "Saroja is Grandma's younger sister; she lives in Coimbatore", [], []),
            _story(_fact("meena", "did", "Meena, Ravi mama's daughter, got engaged", [],
                         [["wedding", "marriage", "கல்யாணம்"], ["engaged", "engagement", "நிச்சயம்"]]),
                   "Meena's wedding", "engaged")]})

    await d.clock(-21)
    await d.apply("Karthik", [], {"entities": [], "ties": [], "facts": [
        _fact("speaker", "did", "went hiking with Mei when she visited home", ["mei"],
              [["hiking", "hike", "hiked", "மலையேற்றம்"], TAMIL_FRIENDS])]})
    await d.apply("Grandma", [], {"entities": [], "ties": [], "facts": [
        _fact("speaker", "did", "joined a bhajan singing group at the temple", [],
              [["music", "singing", "sing", "song", "songs", "bhajan", "பாட்டு", "பஜன்"]])]})
    await d.clock(0)


async def run(args: argparse.Namespace) -> None:
    headers = {"X-KIN-Key": KEY} if KEY else {}
    async with httpx.AsyncClient(base_url=BASE, timeout=90, headers=headers) as http:
        d = Demo(http, wait_s=0)
        await (part1(d) if args.part == 1 else part2(d))
        for name, tok in d.token.items():
            print(f"SIGNIN {name} {tok} {signin_link(tok)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", type=int, choices=(1, 2), default=1)
    try:
        asyncio.run(run(ap.parse_args()))
    except HttpError as e:
        sys.exit(f"seed failed: {e}")


if __name__ == "__main__":
    main()

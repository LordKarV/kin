"""Seed the table demo: Karthik (English) calls his grandmother Paatti (Tamil, played by Nithin).

Two months of planted history so every beat in docs/DEMO_SCRIPT.md fires the first time:
- ~8 weeks ago Karthik told Paatti about his friend Mei, so when he mentions Mei she gets a reminder card in Tamil;
- ~7 weeks ago Mei told Karthik about Lin from the Fudan climbing wall (his world, for the walkthrough);
- ~7 weeks ago Paatti told Karthik about his two uncles named Ravi, so he gets a reminder card for each;
- ~3 weeks ago Karthik went hiking with Mei, which Paatti has not heard (his bridge when she asks about his friends);
- ~2 weeks ago Karthik texted KIN "started bouldering at the campus gym" (private, for the Messages screen).

Uses the demo driver's helpers (dev clock + /api/dev/apply + /api/dev/sms), so every fact goes through the same
validation and visibility rules as a real call or text. Against a fresh server started with DEV_ENDPOINTS=1:

    cd backend && KIN_BASE='http://[::1]:8000' .venv/bin/python ../scripts/seed_karthik_paatti.py
    .venv/bin/python ../scripts/demo_snapshot.py save

--rehearse then plays the table call with typed lines over LiveKit and prints what each phone got. It changes what KIN
thinks they know, so run `demo_snapshot.py restore` after it.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_common_ground import BASE, KEY, Demo, HttpError, _fact, signin_link  # noqa: E402

KARTHIK_PHONE = "+15125550142"
PAATTI_PHONE = "+15125550177"  # Nithin's demo phone number, so Contacts matching still finds him
FRIEND_KEYS = ["friends", "friend", "நண்பர்கள்", "நண்பர்", "ஃப்ரெண்ட்ஸ்"]

# The table call, in order (docs/DEMO_SCRIPT.md). Paatti's lines are Tamil; the judge holds Karthik's phone.
CARE = "கண்ணா, சாப்டியா? ரொம்ப இளைச்சுட்ட மாதிரி இருக்கே."  # Did you eat, dear? You look like you've gotten thin.
RAVIS = "ரவி மாமா சென்னையில இருந்து வந்திருக்கார், ரவி பெரியப்பா மதுரையிலேயே இருக்கார்."  # The two Ravis.
FRIENDS = "உன் நண்பர்கள் எல்லாம் எப்படி இருக்காங்க?"  # How are all your friends?
HIKING = "I went hiking with Mei when she visited!"  # the judge reads the chip out loud
OH_MEI = "ஓ, மெய்! ஷாங்காய்ல படிக்கிற உன் friend தானே?"  # Oh, Mei! Your friend who studies in Shanghai, right?


async def users(d: Demo) -> tuple[str, str, str]:
    for name, lang, phone in [("Karthik", "en", KARTHIK_PHONE), ("Paatti", "ta", PAATTI_PHONE), ("Mei", "en", None)]:
        out = await d.json("/api/users", {"name": name, "lang": lang, "phone": phone})
        d.token[name], d.slug[name] = out["token"], out["person"]
        print(f"user {name} ({lang}) -> {out['person']}")
    k, p, m = d.slug["Karthik"], d.slug["Paatti"], d.slug["Mei"]
    for other, name in [(p, "Paatti"), (m, "Mei")]:  # connected, so People lists both and either can ring
        await d.json("/api/connect", {"slug": other}, "Karthik")
        await d.json(f"/api/connect/{k}/accept", {}, name)
    return k, p, m


async def plant(d: Demo) -> None:
    k, p, m = await users(d)

    # ~8 weeks ago: Karthik's grandmother, and who Mei is to him, said on a call Paatti heard.
    await d.clock(-56)
    placed = await d.json("/api/world/place", {"person": p, "owner": k, "relation": "mother.mother"}, "Karthik")
    print(f"placed Paatti for Karthik: {placed['render']}")
    await d.apply("Karthik", ["Paatti"], {"entities": [], "ties": [
        {"a": "speaker", "b": m, "kind": "friend", "context": "from high school, now in Shanghai"}], "facts": [
        _fact("speaker", "tie", "Mei is Karthik's friend from high school, now in Shanghai", [m], [])]})

    # ~7 weeks ago: Mei's climbing friend Lin (Karthik's world, for the walkthrough).
    await d.clock(-52)
    lin = {"ref": "lin", "name": "Lin", "native": "林", "forms": ["Lin", "Lynn", "林"], "kind": "person",
           "existing_id": None}
    await d.apply("Mei", ["Karthik"], {"entities": [lin], "ties": [
        {"a": "speaker", "b": "lin", "kind": "friend", "context": "from the Fudan climbing wall"}], "facts": [
        _fact("speaker", "tie", "Lin is Mei's friend from the Fudan climbing wall", ["lin"], [])]})

    # ~7 weeks ago: Paatti tells Karthik about his two uncles named Ravi; placed by kin path, by slug, so each is
    # named for who he is (placing the second "Ravi" by name would attach the first one twice). Paatti places them:
    # placing writes "confirmed" evidence for the placer, and Karthik must only have heard them, or no reminder.
    await d.clock(-50)
    ravis = [("ravi_mama", ["ரவி மாமா", "Ravi mama"], "Ravi mama is Karthik's mom's younger brother; he lives in Chennai",
              "ரவி மாமா உங்க அம்மாவோட தம்பி, சென்னையில இருக்கான்", "mother.younger_brother"),
             ("ravi_periyappa", ["ரவி பெரியப்பா", "Ravi periyappa"],
              "Ravi periyappa is Karthik's dad's elder brother; he lives in Madurai",
              "ரவி பெரியப்பா உங்க அப்பாவோட அண்ணன், மதுரையில இருக்காரு", "father.elder_brother")]
    out = await d.apply("Paatti", ["Karthik"], {
        "entities": [{"ref": ref, "name": "Ravi", "native": "ரவி", "forms": forms, "kind": "person",
                      "existing_id": None} for ref, forms, *_ in ravis],
        "ties": [], "facts": [_fact(ref, "relation", text, [], [], src) for ref, _f, text, src, _r in ravis]})
    slug = {e["ref"]: e["slug"] for e in out["entities"]}
    for ref, _f, _t, _s, relation in ravis:
        placed = await d.json("/api/world/place", {"person": slug[ref], "owner": k, "relation": relation}, "Paatti")
        print(f"placed {ref} relative to Karthik: {placed['render']}")

    # ~3 weeks ago: hiking with Mei. Mei was there; Paatti has not heard it, so it is Karthik's bridge.
    await d.clock(-21)
    await d.apply("Karthik", ["Mei"], {"entities": [], "ties": [], "facts": [_fact(
        "speaker", "did", "went hiking with Mei when she visited", [m],
        [["hiking", "hike", "hiked", "மலையேற்றம்"], FRIEND_KEYS])]})

    # ~2 weeks ago: Karthik texts KIN his news. Private; nobody has heard it.
    await d.clock(-14)
    out = await d.json("/api/dev/sms", {"from": KARTHIK_PHONE, "body": "started bouldering at the campus gym"})
    print(f"Karthik texted KIN -> {out['reply']!r}")
    await d.clock(0)


async def rehearse(d: Demo) -> None:
    cid, legs = await d.call("Karthik", "Paatti")
    try:
        await d.say(cid, legs, "Paatti", CARE, {"Karthik": "caption, and a meaning card (from a grandmother, care)"})
        await d.say(cid, legs, "Paatti", RAVIS, {"Karthik": "caption naming each Ravi, and a reminder card for each"})
        await d.say(cid, legs, "Paatti", FRIENDS,
                    {"Karthik": "caption, and the bridge 'You haven't told Paatti: went hiking with Mei'"})
        await d.say(cid, legs, "Karthik", HIKING, {
            "Paatti": "Tamil caption, and a reminder card for Mei, in Tamil",
            "Karthik": "the hiking bridge retracted (he just told her)"})
        await d.say(cid, legs, "Paatti", OH_MEI, {"Karthik": "the caption only (he knows Mei)"})
        await d.say(cid, legs, "Paatti", RAVIS, {"Karthik": "the caption only (he just saw both Ravis)"})
    finally:
        await d.hang_up(legs)


def _pair(value: str, flag: str) -> tuple[str, str]:
    token, sep, slug = value.partition(":")
    if not (token and sep and slug):
        sys.exit(f"--rehearse needs {flag} TOKEN:SLUG (the seed prints both)")
    return token, slug


async def run(args: argparse.Namespace) -> None:
    headers = {"X-KIN-Key": KEY} if KEY else {}
    async with httpx.AsyncClient(base_url=BASE, timeout=90, headers=headers) as http:
        d = Demo(http, wait_s=args.wait)
        if args.rehearse:  # against an already seeded server, as the seeded people
            for name, flag, value in [("Karthik", "--karthik", args.karthik), ("Paatti", "--paatti", args.paatti)]:
                d.token[name], d.slug[name] = _pair(value, flag)
            await rehearse(d)
            return
        await plant(d)
        print("\nSign each phone in (Sign up > Server > Sign-in link), then tap Sign up:")
        for name in ("Karthik", "Paatti"):
            print(f"  {name}: {signin_link(d.token[name])}")
        print(f"\nTo rehearse: --rehearse --karthik {d.token['Karthik']}:{d.slug['Karthik']} "
              f"--paatti {d.token['Paatti']}:{d.slug['Paatti']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rehearse", action="store_true", help="play the table call (needs --karthik and --paatti)")
    ap.add_argument("--karthik", default="", help="TOKEN:SLUG printed by the seed")
    ap.add_argument("--paatti", default="", help="TOKEN:SLUG printed by the seed")
    ap.add_argument("--wait", type=float, default=10.0, help="seconds to wait for cards after each line")
    try:
        asyncio.run(run(ap.parse_args()))
    except HttpError as e:
        sys.exit(f"seed failed: {e}")


if __name__ == "__main__":
    main()

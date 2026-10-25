"""Seed a lived-in history between Karthik and Nithin for the live demo, then print a sign-in link for each phone.

Against a fresh server started with DEV_ENDPOINTS=1. Uses the demo driver's planting helpers (dev clock + /api/dev/apply
+ /api/dev/sms), so every fact goes through the same validation and visibility rules as a real call or text:

    cd backend && .venv/bin/python ../scripts/seed_karthik_nithin.py [--karthik-lang en] [--nithin-lang en]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_common_ground import BASE, KEY, Demo, HttpError, _fact  # noqa: E402

KARTHIK_PHONE = "+15125550142"


async def seed(args: argparse.Namespace) -> None:
    headers = {"X-KIN-Key": KEY} if KEY else {}
    async with httpx.AsyncClient(base_url=BASE, timeout=60, headers=headers) as http:
        d = Demo(http, wait_s=0)
        for name, lang, phone in [("Karthik", args.karthik_lang, KARTHIK_PHONE), ("Nithin", args.nithin_lang, None)]:
            out = await d.json("/api/users", {"name": name, "lang": lang, "phone": phone})
            d.token[name], d.slug[name] = out["token"], out["person"]
            print(f"user {name} ({lang}) -> {out['person']}")
        k, n = d.slug["Karthik"], d.slug["Nithin"]

        # Connected, so either can ring the other without a link.
        await d.json("/api/connect", {"slug": n}, "Karthik")
        await d.json(f"/api/connect/{k}/accept", {}, "Nithin")
        print("connected Karthik <-> Nithin")

        # Who they are to each other (each side's own tie, heard by nobody else).
        await d.apply("Karthik", [], {"entities": [], "ties": [
            {"a": "speaker", "b": n, "kind": "friend", "context": "from freshman year"}], "facts": [
            _fact("speaker", "tie", "Nithin is Karthik's friend from freshman year", [n], [])]})
        await d.apply("Nithin", [], {"entities": [], "ties": [
            {"a": "speaker", "b": k, "kind": "friend", "context": "from freshman year"}], "facts": [
            _fact("speaker", "tie", "Karthik is Nithin's friend from freshman year", [k], [])]})

        # ~8 weeks ago, on a call: Nithin's new climbing friend Rohan.
        await d.clock(-56)
        rohan = {"ref": "rohan", "name": "Rohan", "native": "", "forms": ["Rohan"], "kind": "person", "existing_id": None}
        await d.apply("Nithin", ["Karthik"], {"entities": [rohan], "ties": [
            {"a": "speaker", "b": "rohan", "kind": "friend", "context": "from the climbing gym"}], "facts": [
            _fact("speaker", "tie", "Rohan is Nithin's friend from the climbing gym", ["rohan"], [])]})

        # ~6 and ~4 weeks ago: Nithin's Adobe internship thread, both heard by Karthik.
        await d.clock(-42)
        await d.apply("Nithin", ["Karthik"], {"entities": [], "ties": [], "facts": [{
            **_fact("speaker", "did", "applied for the Adobe internship", [], [["adobe"], ["internship", "intern", "job"]]),
            "storyline": {"existing_id": None, "title": "Adobe internship", "state_label": "applied", "resolved": False}}]})
        await d.clock(-28)
        world = (await http.get("/api/world", headers={"X-KIN-User": d.token["Nithin"]})).json()
        sid = next((s["id"] for s in world.get("storylines", []) if "Adobe" in s.get("title", "")), None)
        await d.apply("Nithin", ["Karthik"], {"entities": [], "ties": [], "facts": [{
            **_fact("speaker", "did", "had the final-round interview for the Adobe internship", [],
                    [["adobe"], ["interview", "final round", "internship"]]),
            "storyline": {"existing_id": sid, "title": "Adobe internship", "state_label": "final round",
                          "resolved": False}}]})

        # ~2 weeks ago: Karthik texts KIN his news. Private; Nithin has not heard it.
        await d.clock(-14)
        out = await d.json("/api/dev/sms", {"from": KARTHIK_PHONE, "body": "started bouldering at the campus gym"})
        print(f"Karthik texted KIN -> {out['reply']!r}")

        await d.clock(0)
        print("\nSign each phone in (Sign up > Server > Sign-in link, or open the link):")
        for name in ("Karthik", "Nithin"):
            print(f"  {name}: kin://signin?token={d.token[name]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--karthik-lang", default="en")
    ap.add_argument("--nithin-lang", default="en")
    try:
        asyncio.run(seed(ap.parse_args()))
    except HttpError as e:
        sys.exit(f"seed failed: {e}")


if __name__ == "__main__":
    main()

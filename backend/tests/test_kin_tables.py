"""Per-language kinship tables for every Muse Voice Transcribe language (25). Tamil is the hand-written gold table;
the others are Muse Spark drafts validated mechanically and flagged verified=false until a speaker checks them."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app.graph.kin_tables import MUSE_LANGUAGES, STEP_WORDS, LanguageTable, all_codes, load_table
from app.graph.kinship import FamilyGraph, Node
from app.graph.linker import Linker
from app.main import app

EXPECTED = {"ar": "Arabic", "bn": "Bengali", "nl": "Dutch", "en": "English", "fr": "French", "de": "German", "he": "Hebrew", "hi": "Hindi", "id": "Indonesian",
            "it": "Italian", "ja": "Japanese", "kn": "Kannada", "ko": "Korean", "ms": "Malay", "zh": "Mandarin Chinese", "mr": "Marathi", "pl": "Polish",
            "pt": "Portuguese", "es": "Spanish", "tl": "Tagalog", "ta": "Tamil", "te": "Telugu", "th": "Thai", "tr": "Turkish", "vi": "Vietnamese"}


def test_muse_language_list_is_the_documented_25():
    assert MUSE_LANGUAGES == EXPECTED
    assert set(all_codes()) == set(EXPECTED)


@pytest.mark.parametrize("code", sorted(EXPECTED))
def test_every_table_loads_and_is_well_formed(code):
    t = load_table(code)
    assert isinstance(t, LanguageTable) and t.code == code and t.name == EXPECTED[code]
    assert t.source in ("hand", "muse-spark-1.3") and isinstance(t.verified, bool)
    assert t.verified == (code == "ta")
    kin = [d for d in t.terms if d.kind == "kin"]
    assert len(kin) >= 12, f"{code}: only {len(kin)} kin terms"
    for d in t.terms:
        assert d.term and d.gloss
        for pat in d.patterns:
            for step in pat.split("."):
                assert step in STEP_WORDS, f"{code}: bad step {step!r} in {d.term}"
        assert (d.kind == "kin") == bool(d.patterns)
    covered = {pat for d in kin for pat in d.patterns}
    assert "mother" in covered and "father" in covered
    assert any(p in covered for p in ("mother.mother", "father.mother", "parent.mother", "parent.parent"))
    assert any(p.startswith(("mother.brother", "father.brother", "parent.brother", "mother.elder_brother", "mother.younger_brother", "father.elder_brother", "father.younger_brother", "parent.sibling")) for p in covered)
    assert t.locale and re.match(r"^[a-z]{2}(-[A-Z]{2})?$", t.locale)


def _family(code: str) -> FamilyGraph:
    people = [Node(1, "p_kid", "Kid", "", "m", 2008, True, False, "", [("Kid", "en", "name")]),
              Node(2, "p_mom", "Mira", "", "f", 1980, False, False, "", [("Mira", "en", "name")]),
              Node(3, "p_dad", "Dan", "", "m", 1978, False, False, "", [("Dan", "en", "name")]),
              Node(4, "p_gran", "Gran", "", "f", 1952, False, False, "", [("Gran", "en", "name")]),
              Node(5, "p_uncle", "Umar", "", "m", 1984, False, False, "", [("Umar", "en", "name")])]
    edges = [(2, 1, "parent", "", {}), (3, 1, "parent", "", {}), (4, 2, "parent", "", {}), (4, 5, "parent", "", {}), (2, 5, "sibling", "", {"src_is_elder": True})]
    return FamilyGraph(1, code, people, edges, [])


@pytest.mark.parametrize("code", sorted(EXPECTED))
def test_resolver_and_linker_work_in_every_language(code):
    t = load_table(code)
    g = _family(code)
    mother = next(d for d in t.terms if "mother" in d.patterns)
    assert g.resolve_kin_term(mother, 1) == {2}
    linker = Linker(g)
    spans = linker.link(f"{mother.script or mother.term} Dan", speaker="p_gran", listener="p_kid")
    assert "p_mom" in {s.node for s in spans}, f"{code}: {mother.term} not linked"
    assert "p_dad" in {s.node for s in spans}
    # the uncle (b. 1984) is Mom's YOUNGER brother: at least one term for that relation must resolve to him
    fits = [d for d in t.terms if any(p in ("mother.brother", "mother.younger_brother", "parent.brother", "parent.sibling", "mother.sibling") for p in d.patterns)]
    if fits:
        assert any(5 in g.resolve_kin_term(d, 1) for d in fits), f"{code}: none of {[d.term for d in fits]} resolves Mom's younger brother"


def test_tamil_table_matches_hand_ontology():
    from app.graph.ontology import KIN_TERMS
    t = load_table("ta")
    assert {d.term for d in t.terms} == {d.term for d in KIN_TERMS}
    assert "்" in t.final_strip and "kku" in t.roman_suffixes and "என்" in t.possessive_speaker


def test_tables_seeded_into_db_and_listed_by_api():
    with TestClient(app) as c:
        langs = c.get("/api/languages").json()
    by = {l["code"]: l for l in langs}
    assert len(by) == 25 and by["ta"]["verified"] is True and by["hi"]["verified"] is False
    assert by["te"]["kin_terms"] >= 12 and by["ta"]["name"] == "Tamil"


def test_family_language_can_be_switched_and_translator_follows():
    with TestClient(app) as c:
        r = c.patch("/api/family/language", json={"code": "hi"})
        assert r.status_code == 200 and r.json()["heritage_lang"] == "hi"
        g = c.get("/api/family/graph").json()
        assert g["heritage_lang"] == "hi"
        from app.mt.translate import get_translator
        tr = get_translator(1)
        assert tr.lang == "Hindi" and "HINDI KIN TERMS" in tr.system_prompt("p_arjun")
        assert c.patch("/api/family/language", json={"code": "xx"}).status_code == 400
        c.patch("/api/family/language", json={"code": "ta"})


def test_muse_asr_language_bias_uses_names_not_codes():
    from app.audio.asr import make_asr
    from app.audio.asr_muse import MuseASR
    import os
    os.environ["ASR_PROVIDER"] = "muse"; os.environ["MODEL_API_KEY"] = "k"
    from app.config import get_settings
    get_settings.cache_clear()
    asr = make_asr(language="ta", keyterms=["Ravi"])
    assert isinstance(asr, MuseASR) and asr.handshake["languageBias"] == ["Tamil", "English"]

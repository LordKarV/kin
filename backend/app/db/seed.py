"""The demo family: the Krishnans, a Tamil family split between Madurai, Chennai, Coimbatore, Singapore and Austin.

Fictional but realistic. Two people share the first name Ravi (the "Ravi problem"):
  - Ravi mama        = Priya's younger brother  = Arjun's maternal uncle (Mom's brother), Chennai
  - Ravi periyappa   = Senthil's elder brother  = Arjun's paternal uncle (Dad's elder brother), Coimbatore
Listener/learner is Arjun (grandchild, Austin). Primary speaker is Kamala Paatti (maternal grandmother, Madurai).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..graph.ontology import KIN_TERMS
from . import models as m

FAMILY_NAME = "Krishnan family"

# slug, display, tamil, gender, birth, notes, aliases(list of (alias, lang, kind)), learner, deceased
PEOPLE = [
    ("p_arjun", "Arjun", "அர்ஜுன்", "m", 2005, "Grandchild, UT Austin student; learning Tamil. The listener.",
     [("Arjun", "en", "name"), ("அர்ஜுன்", "ta", "script"), ("Arju", "en", "nickname"), ("அர்ஜு", "ta", "nickname"), ("Kanna", "ta", "address"), ("கண்ணா", "ta", "address")], True, False),
    ("p_kamala", "Kamala", "கமலா", "f", 1951, "Maternal grandmother (Paatti) in Madurai. Primary speaker. Knee trouble; grows curry leaves on the terrace.",
     [("Kamala", "en", "name"), ("கமலா", "ta", "script"), ("Paatti", "ta", "address"), ("பாட்டி", "ta", "address"), ("Ammamma", "ta", "address"), ("அம்மம்மா", "ta", "address")], False, False),
    ("p_raghavan", "Raghavan", "ராகவன்", "m", 1946, "Maternal grandfather (Thatha), passed away 2019. Was a schoolteacher.",
     [("Raghavan", "en", "name"), ("ராகவன்", "ta", "script"), ("Thatha", "ta", "address"), ("தாத்தா", "ta", "address")], False, True),
    ("p_priya", "Priya", "பிரியா", "f", 1976, "Arjun's mother; Kamala's daughter. Paatti calls her Pappa.",
     [("Priya", "en", "name"), ("பிரியா", "ta", "script"), ("Pappa", "ta", "nickname"), ("பாப்பா", "ta", "nickname"), ("Amma", "ta", "address"), ("அம்மா", "ta", "address")], False, False),
    ("p_senthil", "Senthil", "செந்தில்", "m", 1973, "Arjun's father; from Coimbatore.",
     [("Senthil", "en", "name"), ("செந்தில்", "ta", "script"), ("Appa", "ta", "address"), ("அப்பா", "ta", "address")], False, False),
    ("p_ravi_mama", "Ravi", "ரவி", "m", 1980, "Priya's younger brother (Kamala's son). Lives in Adyar, Chennai. Bank job. Arjun's maternal uncle.",
     [("Ravi", "en", "name"), ("ரவி", "ta", "script"), ("Ravi mama", "ta", "address"), ("ரவி மாமா", "ta", "address"), ("Ravi kutty", "ta", "nickname")], False, False),
    ("p_ravi_periyappa", "Ravi", "ரவி", "m", 1969, "Senthil's elder brother. Lives in Coimbatore, runs a textile shop. Arjun's paternal uncle.",
     [("Ravi", "en", "name"), ("ரவி", "ta", "script"), ("Ravi periyappa", "ta", "address"), ("ரவி பெரியப்பா", "ta", "address")], False, False),
    ("p_lakshmi", "Lakshmi", "லட்சுமி", "f", 1984, "Ravi mama's wife. Chennai. Teaches Bharatanatyam.",
     [("Lakshmi", "en", "name"), ("லட்சுமி", "ta", "script"), ("Lakshmi mami", "ta", "address"), ("லட்சுமி மாமி", "ta", "address")], False, False),
    ("p_meena", "Meena", "மீனா", "f", 1978, "Senthil's younger sister. Lives in Singapore. Arjun's paternal aunt.",
     [("Meena", "en", "name"), ("மீனா", "ta", "script"), ("Meena atthai", "ta", "address"), ("மீனா அத்தை", "ta", "address")], False, False),
    ("p_divya", "Divya", "திவ்யா", "f", 2001, "Arjun's elder sister. Doctor in Houston. Family nickname Chinnu.",
     [("Divya", "en", "name"), ("திவ்யா", "ta", "script"), ("Chinnu", "ta", "nickname"), ("சின்னு", "ta", "nickname"), ("Divya akka", "ta", "address"), ("திவ்யா அக்கா", "ta", "address")], False, False),
    ("p_karthik", "Karthik", "கார்த்திக்", "m", 2010, "Ravi mama and Lakshmi's son. Arjun's younger cousin, Chennai. Plays cricket.",
     [("Karthik", "en", "name"), ("கார்த்திக்", "ta", "script"), ("Karthik thambi", "ta", "address")], False, False),
    ("p_vishnu", "Vishnu", "விஷ்ணு", "m", 1998, "Ravi periyappa's son. Arjun's elder cousin, Coimbatore. Getting married next year.",
     [("Vishnu", "en", "name"), ("விஷ்ணு", "ta", "script"), ("Vishnu anna", "ta", "address"), ("விஷ்ணு அண்ணா", "ta", "address")], False, False),
    ("p_saroja", "Saroja", "சரோஜா", "f", 1956, "Kamala's younger sister. Lives next street in Madurai. Arjun's grand-aunt (chinna paatti).",
     [("Saroja", "en", "name"), ("சரோஜா", "ta", "script"), ("Chinna paatti", "ta", "address"), ("சின்ன பாட்டி", "ta", "address")], False, False),
]

# (src, dst, relation, lang_term(how dst addresses src), meta)
EDGES = [
    ("p_raghavan", "p_kamala", "spouse", "", {}),
    ("p_kamala", "p_priya", "parent", "Amma", {}),
    ("p_raghavan", "p_priya", "parent", "Appa", {}),
    ("p_kamala", "p_ravi_mama", "parent", "Amma", {}),
    ("p_raghavan", "p_ravi_mama", "parent", "Appa", {}),
    ("p_priya", "p_ravi_mama", "sibling", "Akka", {"src_is_elder": True}),
    ("p_kamala", "p_saroja", "sibling", "Akka", {"src_is_elder": True}),
    ("p_senthil", "p_priya", "spouse", "", {}),
    ("p_priya", "p_arjun", "parent", "Amma", {}),
    ("p_senthil", "p_arjun", "parent", "Appa", {}),
    ("p_priya", "p_divya", "parent", "Amma", {}),
    ("p_senthil", "p_divya", "parent", "Appa", {}),
    ("p_divya", "p_arjun", "sibling", "Akka", {"src_is_elder": True}),
    ("p_ravi_periyappa", "p_senthil", "sibling", "Anna", {"src_is_elder": True}),
    ("p_senthil", "p_meena", "sibling", "Anna", {"src_is_elder": True}),
    ("p_ravi_periyappa", "p_meena", "sibling", "Anna", {"src_is_elder": True}),
    ("p_ravi_mama", "p_lakshmi", "spouse", "", {}),
    ("p_ravi_mama", "p_karthik", "parent", "Appa", {}),
    ("p_lakshmi", "p_karthik", "parent", "Amma", {}),
    ("p_ravi_periyappa", "p_vishnu", "parent", "Appa", {}),
]

# slug, kind, name, tamil, aliases, note
THINGS = [
    ("d_rasam", "dish", "rasam", "ரசம்", ["rasam", "ரசம்", "milagu rasam", "மிளகு ரசம்"], "Paatti's pepper rasam; the cure for every cold in this family. Not 'soup'."),
    ("d_sambar", "dish", "sambar", "சாம்பார்", ["sambar", "sambhar", "சாம்பார்"], "Sunday sambar with drumstick (murungakkai). Priya's version is sweeter; Paatti disapproves."),
    ("d_pongal", "dish", "ven pongal", "வெண் பொங்கல்", ["pongal", "ven pongal", "பொங்கல்", "வெண் பொங்கல்", "sakkarai pongal", "சக்கரை பொங்கல்"], "Made every Pongal morning; sakkarai (sweet) pongal is Arjun's favourite."),
    ("d_murukku", "dish", "murukku", "முறுக்கு", ["murukku", "முறுக்கு", "murukku tin"], "Paatti's Deepavali murukku, shipped to Austin in a Horlicks tin every year."),
    ("d_payasam", "dish", "paal payasam", "பால் பாயசம்", ["payasam", "paal payasam", "பாயசம்", "பால் பாயசம்", "semiya payasam"], "Birthday dish. Thatha used to make the semiya version."),
    ("d_kozhukattai", "dish", "kozhukattai", "கொழுக்கட்டை", ["kozhukattai", "kolukattai", "கொழுக்கட்டை", "modakam"], "Steamed dumplings for Vinayagar Chaturthi; Divya pleats them, Arjun eats them."),
    ("pl_madurai_house", "place", "the Madurai house", "மதுரை வீடு", ["Madurai", "மதுரை", "K.K. Nagar", "கே.கே. நகர்", "veedu", "வீடு", "ooru", "ஊரு", "ஊர்", "mottai maadi", "மொட்டை மாடி", "terrace"], "Paatti's home in K.K. Nagar, Madurai, with the terrace garden. 'Ooru' means this house, not just 'town'."),
    ("pl_meenakshi_kovil", "place", "Meenakshi Amman temple", "மீனாட்சி அம்மன் கோவில்", ["Meenakshi kovil", "மீனாட்சி கோவில்", "kovil", "கோவில்", "Meenakshi Amman temple"], "The temple Paatti walks to every Friday. 'Kovil' alone means this one."),
    ("pl_adyar", "place", "Ravi mama's flat in Adyar", "அடையாறு", ["Adyar", "அடையாறு", "Chennai", "சென்னை", "Madras", "மெட்ராஸ்"], "Ravi mama and Lakshmi mami's flat in Chennai. Family stays there on the way to Madurai."),
    ("pl_coimbatore", "place", "Coimbatore", "கோயம்புத்தூர்", ["Coimbatore", "Kovai", "கோவை", "கோயம்புத்தூர்"], "Appa's side: Ravi periyappa's house and textile shop."),
    ("pl_austin", "place", "Austin", "ஆஸ்டின்", ["Austin", "ஆஸ்டின்", "America", "அமெரிக்கா", "US"], "Where Arjun and his parents live."),
    ("ev_pongal", "event", "Pongal", "பொங்கல்", ["Pongal", "பொங்கல்", "Thai Pongal", "தைப்பொங்கல்"], "Harvest festival, mid-January. The whole family video-calls from the Madurai terrace at sunrise."),
    ("ev_deepavali", "event", "Deepavali", "தீபாவளி", ["Deepavali", "Diwali", "தீபாவளி"], "October/November. Oil bath at 4 a.m., new clothes, murukku tin goes to Austin."),
    ("ev_thatha_thithi", "event", "Thatha's thithi", "தாத்தா திதி", ["thithi", "திதி", "Thatha's anniversary"], "Raghavan Thatha's annual remembrance in March. Paatti makes his semiya payasam."),
    ("ev_vishnu_wedding", "event", "Vishnu's wedding", "விஷ்ணு கல்யாணம்", ["kalyanam", "கல்யாணம்", "Vishnu's wedding"], "Next year in Coimbatore; Arjun is expected to come."),
]


def seed_demo_family(session: Session) -> m.Family:
    """Create (or return the existing) demo family. Idempotent by family name."""
    fam = session.scalar(select(m.Family).where(m.Family.name == FAMILY_NAME))
    if fam is None:
        fam = m.Family(name=FAMILY_NAME, heritage_lang="ta")
        session.add(fam)
        session.flush()

    by_slug: dict[str, m.Person] = {p.slug: p for p in session.scalars(select(m.Person).where(m.Person.family_id == fam.id))}
    for slug, name, ta, g, by, notes, aliases, learner, dead in PEOPLE:
        if slug in by_slug:
            continue
        p = m.Person(family_id=fam.id, slug=slug, display_name=name, lang_name=ta, gender=g, birth_year_approx=by,
                     notes=notes, is_learner=learner, is_deceased=dead)
        p.aliases = [m.Alias(alias=a, lang=l, kind=k) for a, l, k in aliases]
        session.add(p)
        by_slug[slug] = p
    session.flush()

    existing_edges = {(e.src_person, e.dst_person, e.relation) for e in session.scalars(select(m.Edge).where(m.Edge.family_id == fam.id))}
    for src, dst, rel, term, meta in EDGES:
        key = (by_slug[src].id, by_slug[dst].id, rel)
        if key not in existing_edges:
            session.add(m.Edge(family_id=fam.id, src_person=key[0], dst_person=key[1], relation=rel, lang_term=term, meta=meta))

    existing_things = {t.slug for t in session.scalars(select(m.Thing).where(m.Thing.family_id == fam.id))}
    for slug, kind, name, ta, aliases, note in THINGS:
        if slug not in existing_things:
            session.add(m.Thing(family_id=fam.id, slug=slug, kind=kind, name=name, lang_name=ta, aliases=aliases, note=note))

    if session.scalar(select(m.KinTerm).where(m.KinTerm.lang == "ta", m.KinTerm.family_id.is_(None))) is None:
        for t in KIN_TERMS:
            session.add(m.KinTerm(family_id=None, lang="ta", term=t.term, script_form=t.script, kind=t.kind,
                                  relation_patterns=list(t.patterns), gloss=t.gloss, notes=t.notes))

    # consent record for the demo grandparent (voice clone uses a teammate's voice in the demo; see plan §9)
    kamala = by_slug["p_kamala"]
    if session.scalar(select(m.Consent).where(m.Consent.person_id == kamala.id)) is None:
        session.add(m.Consent(person_id=kamala.id, voice_clone=False, memory=True))
    session.flush()
    return fam

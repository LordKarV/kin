"""Tamil kinship ontology: kin term → structured relation patterns relative to the speaker ("ego").

Pattern grammar (dot-separated steps from ego to the referent):
  mother father parent spouse husband wife son daughter child
  brother sister sibling  elder_brother younger_brother elder_sister younger_sister
Example: mama → "mother.brother" (mother's brother). Several patterns = context-dependent term.
Family-specific usage on Edge.lang_term always overrides these defaults.
Sources: standard Tamil kin terminology (Dravidian system; cross/parallel cousin distinction), Kinbank-style tables.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True)
class KinTermDef:
    term: str                 # canonical romanized form
    script: str               # Tamil script
    patterns: tuple[str, ...]  # relation patterns from ego
    gloss: str                # short English gloss for the UI
    kind: str = "kin"         # kin | endearment | honorific
    variants: tuple[str, ...] = field(default_factory=tuple)  # extra romanizations/scripts
    notes: str = ""


KIN_TERMS: list[KinTermDef] = [
    KinTermDef("amma", "அம்மா", ("mother",), "mother", variants=("ammaa",)),
    KinTermDef("appa", "அப்பா", ("father",), "father", variants=("appaa",)),
    KinTermDef("paatti", "பாட்டி", ("mother.mother", "father.mother"), "grandmother", variants=("patti", "paati", "pati")),
    KinTermDef("ammamma", "அம்மம்மா", ("mother.mother",), "maternal grandmother", variants=("ammama",), notes="Used by some Tamil families; more common in Telugu/Malayalam."),
    KinTermDef("thatha", "தாத்தா", ("mother.father", "father.father"), "grandfather", variants=("thaatha", "tata", "thata")),
    KinTermDef("periya paatti", "பெரிய பாட்டி", ("mother.mother.elder_sister", "father.mother.elder_sister", "mother.father.elder_brother.wife"), "grandmother's elder sister", variants=("periya patti", "periyapaatti")),
    KinTermDef("chinna paatti", "சின்ன பாட்டி", ("mother.mother.younger_sister", "father.mother.younger_sister", "mother.father.younger_brother.wife"), "grandmother's younger sister", variants=("chinna patti", "chinnapaatti", "chithi paatti")),
    KinTermDef("mama", "மாமா", ("mother.brother", "father.sister.husband", "spouse.father"), "maternal uncle", variants=("maama", "mamaa", "maamaa"), notes="Also father-in-law; also a polite address for any older man."),
    KinTermDef("mami", "மாமி", ("mother.brother.wife", "spouse.mother"), "maternal uncle's wife", variants=("maami",), notes="Also mother-in-law in some families; polite address for an older woman."),
    KinTermDef("atthai", "அத்தை", ("father.sister", "spouse.mother"), "paternal aunt", variants=("athai", "aththai", "attai")),
    KinTermDef("periyappa", "பெரியப்பா", ("father.elder_brother", "mother.elder_sister.husband"), "father's elder brother", variants=("periappa", "periyappaa", "periya appa")),
    KinTermDef("periyamma", "பெரியம்மா", ("mother.elder_sister", "father.elder_brother.wife"), "mother's elder sister", variants=("periamma", "periya amma")),
    KinTermDef("chithappa", "சித்தப்பா", ("father.younger_brother", "mother.younger_sister.husband"), "father's younger brother", variants=("chithappaa", "chiththappa", "sithappa", "chitthappa")),
    KinTermDef("chithi", "சித்தி", ("mother.younger_sister", "father.younger_brother.wife"), "mother's younger sister", variants=("chiththi", "sithi", "chitti")),
    KinTermDef("anna", "அண்ணா", ("elder_brother", "father.brother.son", "mother.sister.son"), "elder brother", variants=("annan", "annaa", "அண்ணன்"), notes="Also parallel cousins and any older male; polite address."),
    KinTermDef("akka", "அக்கா", ("elder_sister", "father.brother.daughter", "mother.sister.daughter"), "elder sister", variants=("akkaa",), notes="Also parallel cousins and any older female; polite address."),
    KinTermDef("thambi", "தம்பி", ("younger_brother", "father.brother.son", "mother.sister.son"), "younger brother", variants=("thampi", "tambi")),
    KinTermDef("thangai", "தங்கை", ("younger_sister", "father.brother.daughter", "mother.sister.daughter"), "younger sister", variants=("thangachi", "தங்கச்சி", "thangachchi")),
    KinTermDef("machan", "மச்சான்", ("mother.brother.son", "father.sister.son", "wife.brother", "sister.husband"), "cross-cousin / brother-in-law", variants=("machaan", "machi", "maccan"), notes="Among young men, any close friend."),
    KinTermDef("athaan", "அத்தான்", ("mother.brother.son", "father.sister.son"), "elder cross-cousin (male)", variants=("attan", "athan")),
    KinTermDef("maapillai", "மாப்பிள்ளை", ("daughter.husband", "sister.husband"), "son-in-law", variants=("mapillai", "maaplai", "mappillai")),
    KinTermDef("marumagal", "மருமகள்", ("son.wife",), "daughter-in-law", variants=("marumagal",)),
    KinTermDef("marumagan", "மருமகன்", ("daughter.husband", "sister.son"), "son-in-law / nephew", variants=()),
    KinTermDef("magan", "மகன்", ("son",), "son", variants=("magane", "மகனே")),
    KinTermDef("paiyan", "பையன்", ("son",), "son (lit. boy)", variants=("paiyyan", "payyan"), notes="Only a kin term after a head ('mama paiyan') or a possessive ('en paiyan'); bare, it just means boy."),
    KinTermDef("magal", "மகள்", ("daughter",), "daughter", variants=("magale", "மகளே", "ponnu", "பொண்ணு")),
    KinTermDef("peran", "பேரன்", ("son.son", "daughter.son"), "grandson", variants=("pera", "பேரா", "perane")),
    KinTermDef("pethi", "பேத்தி", ("son.daughter", "daughter.daughter"), "granddaughter", variants=("peththi",)),
    KinTermDef("kozhundhan", "கொழுந்தன்", ("husband.younger_brother",), "husband's younger brother", variants=("kozhunthan",)),
    KinTermDef("naathanaar", "நாத்தனார்", ("husband.sister",), "husband's sister", variants=("nathanar", "naathanar")),
    KinTermDef("sammandhi", "சம்மந்தி", ("child.spouse.parent",), "co-parent-in-law", variants=("sambandhi",)),
    KinTermDef("purushan", "புருஷன்", ("husband",), "husband", variants=("kanavar", "கணவர்")),
    KinTermDef("pondatti", "பொண்டாட்டி", ("wife",), "wife", variants=("manaivi", "மனைவி")),
    # Endearments / address forms (not relations; never grounded to a node by themselves)
    KinTermDef("kanna", "கண்ணா", (), "dear (lit. 'my eye')", kind="endearment", variants=("kannu", "கண்ணு", "kannaa")),
    KinTermDef("chellam", "செல்லம்", (), "darling", kind="endearment", variants=("sellam",)),
    KinTermDef("da", "டா", (), "informal address to a male (intimate)", kind="endearment", variants=()),
    KinTermDef("di", "டி", (), "informal address to a female (intimate)", kind="endearment", variants=()),
    KinTermDef("nga", "ங்க", (), "respectful plural suffix (-nga)", kind="honorific", variants=("-nga",)),
]

_INDEX: dict[str, KinTermDef] = {}


def normalize_term(s: str) -> str:
    """Lowercase, NFC, collapse doubled long vowels (maamaa→mama), drop punctuation."""
    s = unicodedata.normalize("NFC", s).strip().lower()
    s = re.sub(r"[^\w\s஀-௿]", "", s)
    s = re.sub(r"\s+", " ", s)
    if re.search(r"[a-z]", s):
        s = re.sub(r"aa", "a", s)
        s = re.sub(r"ee", "e", s)  # keep 'ii' for e.g. 'thiithi'? Not a kin term; fine.
        s = re.sub(r"oo", "o", s)
        s = re.sub(r"th+", "th", s)
    return s


for _t in KIN_TERMS:
    for _k in (_t.term, _t.script, *_t.variants):
        _INDEX.setdefault(normalize_term(_k), _t)


def lookup(term: str) -> KinTermDef | None:
    return _INDEX.get(normalize_term(term))


def all_surface_forms() -> dict[str, KinTermDef]:
    """normalized surface → def (for the linker's scan)."""
    return dict(_INDEX)

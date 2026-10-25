"""Who just spoke on a merged phone call? One audio stream carries both people, and Muse Voice Transcribe returns
text without a language label, so the language of the text decides the direction (as Hey Buddy does)."""
from __future__ import annotations

import re
import unicodedata

_ENGLISH = frozenset(
    "a an the and or but if so i me my mine you your yours he him his she her hers it its we us our they them their "
    "is are was were be been am do does did done have has had will would can could should to of in on at for with "
    "from that this these those what when where why how who not no yes ok okay yeah hi hello hey bye please thanks "
    "thank just too also very really there here got get going go miss love tell said say".split()
)

# ponytail: function-word ratio, not a language-ID model; a heritage sentence full of "a"/"no" (Spanish) can flip.
# Upgrade path: ask the MT call to report the source language.
_ENGLISH_RATIO = 0.25
_NON_LATIN_RATIO = 0.3


def is_heritage(text: str, heritage_lang: str) -> bool:
    """True if `text` is in the family's heritage language, False if it is English."""
    if heritage_lang.split("-")[0].lower() == "en":
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    non_latin = sum(1 for c in letters if not unicodedata.name(c, "").startswith("LATIN"))
    if non_latin / len(letters) > _NON_LATIN_RATIO:
        return True
    words = re.findall(r"[a-z']+", text.lower())
    return bool(words) and sum(w in _ENGLISH for w in words) / len(words) < _ENGLISH_RATIO

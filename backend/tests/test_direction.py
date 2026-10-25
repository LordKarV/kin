"""Merged phone call: one audio stream, two people. The language of each utterance decides the direction."""
import pytest

from app.audio.direction import is_heritage


@pytest.mark.parametrize("text,lang,expected", [
    ("ரவி நேத்து அடையாறுல இருந்து போன் பண்ணினான்.", "ta", True),
    ("Tell Grandma I finished my exams and I miss her cooking.", "ta", False),
    ("नानी, मैंने खाना खा लिया", "hi", True),
    ("Ravi nettu Adyar pongal pannnaan.", "ta", True),       # romanized Tamil from the ASR
    ("¿Ya comiste, mijo? Te hice tamales.", "es", True),     # Latin-script heritage language
    ("Did you eat yet? I made tamales.", "es", False),
    ("Okay, bye Paatti!", "ta", False),                      # short English with a kin term
    ("ok", "ta", False),
])
def test_is_heritage(text, lang, expected):
    assert is_heritage(text, lang) is expected


def test_english_heritage_never_flips():
    assert is_heritage("hello there", "en") is False

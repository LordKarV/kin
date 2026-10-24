"""Provider adapters: pure request builders and message parsers (no network)."""
import json
from urllib.parse import parse_qs, urlparse

from app.audio.asr import ASREvent
from app.audio.asr_deepgram import deepgram_url, parse_deepgram_message
from app.audio.asr_muse import muse_handshake, parse_muse_event


def test_deepgram_url_has_verified_params_and_repeated_keyterms():
    url = deepgram_url(language="ta", sample_rate=16000, keyterms=["Ravi mama", "rasam", "Adyar"])
    u = urlparse(url)
    assert u.scheme == "wss" and u.netloc == "api.deepgram.com" and u.path == "/v1/listen"
    q = parse_qs(u.query)
    assert q["model"] == ["nova-3"] and q["language"] == ["ta"] and q["encoding"] == ["linear16"]
    assert q["sample_rate"] == ["16000"] and q["interim_results"] == ["true"]
    assert q["keyterm"] == ["Ravi mama", "rasam", "Adyar"]


def test_deepgram_keyterms_capped_to_100():
    q = parse_qs(urlparse(deepgram_url("en", 16000, [f"k{i}" for i in range(150)])).query)
    assert len(q["keyterm"]) == 100


def test_parse_deepgram_results_final_with_words():
    msg = {"type": "Results", "is_final": True, "speech_final": True, "start": 1.2, "duration": 0.8,
           "channel": {"alternatives": [{"transcript": "உன் மாமா", "confidence": 0.9,
                                         "words": [{"word": "உன்", "start": 1.2, "end": 1.4, "language": "ta"}, {"word": "மாமா", "start": 1.4, "end": 2.0, "language": "ta"}]}]}}
    ev = parse_deepgram_message(json.dumps(msg))
    assert isinstance(ev, ASREvent) and ev.final and ev.text == "உன் மாமா"
    assert ev.t_start == 1.2 and ev.t_end == 2.0 and ev.lang_tags == ["ta"]
    assert parse_deepgram_message(json.dumps({"type": "Metadata"})) is None
    assert parse_deepgram_message(json.dumps({"type": "Results", "is_final": False, "channel": {"alternatives": [{"transcript": ""}]}})) is None


def test_muse_handshake_matches_docs():
    hs = muse_handshake(api_key="abc", keywords=["Ravi", "rasam"], language_bias=["ta", "en"])
    assert hs["authorization"] == {"accessToken": "Bearer abc"}
    assert hs["audioEncoding"] == "PCM_16KHZ" and hs["mode"] == "ENDPOINTING" and hs["partialMode"] == "CUMULATIVE"
    assert hs["keywords"] == ["Ravi", "rasam"] and hs["languageBias"] == ["ta", "en"]


def test_parse_muse_events():
    assert parse_muse_event({"sessionId": "s1"}) is None
    p = parse_muse_event({"type": "transcript", "transcript": "உன் மா", "final": False, "audioProcessedMs": 900})
    assert p and not p.final and p.text == "உன் மா"
    f = parse_muse_event({"type": "speechComplete", "turnId": "t1", "transcript": "உன் மாமா நேத்து போன் பண்ணான்."})
    assert f and f.final and f.turn_id == "t1"
    assert parse_muse_event({"type": "speechEnd", "turnId": "t1"}) is None

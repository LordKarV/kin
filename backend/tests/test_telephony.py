"""Phone audio: Twilio Media Streams carry 8 kHz mu-law; the pipeline speaks 16 kHz PCM16."""
import math
import struct

from app.audio.telephony import from_twilio, mulaw_decode, mulaw_encode, to_twilio


def _pcm(samples):
    return struct.pack(f"<{len(samples)}h", *samples)


def _unpack(b):
    return struct.unpack(f"<{len(b) // 2}h", b)


def test_mulaw_round_trip_is_close():
    src = [0, 1, -1, 100, -100, 1000, -1000, 8000, -8000, 32000, -32000]
    back = _unpack(mulaw_decode(mulaw_encode(_pcm(src))))
    for a, b in zip(src, back):
        assert abs(a - b) <= max(8, abs(a) * 0.07), (a, b)  # mu-law is ~7% relative error at most


def test_known_mulaw_codes():
    assert mulaw_encode(_pcm([0])) == b"\xff"  # G.711 silence
    assert _unpack(mulaw_decode(b"\xff")) == (0,)


def test_twilio_frames_resample_both_ways():
    tone = [int(8000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(320)]  # 20 ms at 16 kHz
    out = to_twilio(_pcm(tone))
    assert len(out) == 160  # 20 ms at 8 kHz, one byte per sample
    assert len(from_twilio(out)) == 320 * 2  # back to 20 ms of 16 kHz PCM16


def test_odd_length_input_does_not_crash():
    assert to_twilio(b"\x01") == b""
    assert len(to_twilio(_pcm([1, 2, 3]))) == 1

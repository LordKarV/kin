"""Phone-line audio: Twilio Media Streams carry 8 kHz mono G.711 mu-law; the pipeline speaks 16 kHz mono PCM16.

Plain Python (audioop is gone in 3.13). One 20 ms Twilio frame is 160 samples, so this is cheap enough per call.
"""
from __future__ import annotations

import struct

_BIAS = 0x84
_CLIP = 32635


def _decode(u: int) -> int:
    u = ~u & 0xFF
    sample = (((u & 0x0F) << 3) + _BIAS) << ((u >> 4) & 0x07)
    sample -= _BIAS
    return -sample if u & 0x80 else sample


def _encode(sample: int) -> int:
    sign = 0x80 if sample < 0 else 0
    sample = min(-sample if sign else sample, _CLIP) + _BIAS
    exponent = max(0, ((sample >> 7) & 0xFF).bit_length() - 1)
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


_DECODE = tuple(_decode(u) for u in range(256))


def mulaw_decode(data: bytes) -> bytes:
    return struct.pack(f"<{len(data)}h", *(_DECODE[b] for b in data))


def mulaw_encode(pcm16: bytes) -> bytes:
    n = len(pcm16) // 2
    return bytes(_encode(s) for s in struct.unpack(f"<{n}h", pcm16[: n * 2]))


def from_twilio(mulaw: bytes) -> bytes:
    """8 kHz mu-law -> 16 kHz PCM16 (linear interpolation)."""
    s = [_DECODE[b] for b in mulaw]
    out: list[int] = []
    for i, v in enumerate(s):
        out += (v, (v + s[i + 1]) // 2 if i + 1 < len(s) else v)
    return struct.pack(f"<{len(out)}h", *out)


def to_twilio(pcm16: bytes) -> bytes:
    """16 kHz PCM16 -> 8 kHz mu-law (average each pair: a crude low-pass, fine for speech)."""
    n = len(pcm16) // 2
    s = struct.unpack(f"<{n}h", pcm16[: n * 2])
    return bytes(_encode((s[i] + s[i + 1]) // 2) for i in range(0, n - 1, 2))

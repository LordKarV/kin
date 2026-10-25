"""KIN as the third leg of a merged phone call (the Hey Buddy pattern).

The grandchild calls the grandparent as usual, taps "Add call", dials KIN's number and merges. Twilio then streams
the merged audio, both people mixed, to /twilio/buddy/stream/{call_id}. One bilingual ASR stream hears everyone; the
language of each finished utterance decides who spoke; the grounded translation is spoken back into the call, so the
grandparent hears the heritage language and the grandchild hears English. Everything else (linker, Fade, glossary,
persistence, latency) is the normal CallSession pipeline.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .direction import is_heritage
from .pipeline import CallSession
from .telephony import to_twilio

SendAudio = Callable[[bytes], Awaitable[None]]  # mu-law 8 kHz bytes into the call
GREETING = "Hi, this is KIN. I will interpret for you both."


def default_people(g) -> tuple[str, str]:
    """(elder, learner) slugs for a merged call: the family's eldest living member and its learner."""
    return g.elder_slug(), g.learner_slug()


class BuddyLine:
    def __init__(self, session: CallSession, send_audio: SendAudio, grandparent: str, learner: str):
        self.session, self.send_audio = session, send_audio
        self.grandparent, self.learner = grandparent, learner

    async def attach(self) -> None:
        # both people are on the one phone line: two pipeline sides, one shared ASR, TTS of either goes into the call
        for role, person in (("grandparent", self.grandparent), ("grandchild", self.learner)):
            await self.session.join(role, person, _ignore, self._play, start_asr=False)
        self.session.phone_line = True

    async def detach(self) -> None:
        self.session.phone_line = False
        for role in ("grandparent", "grandchild"):
            await self.session.leave(role)

    async def on_final(self, text: str) -> dict:
        role = "grandparent" if is_heritage(text, self.session.translator.g.heritage_lang) else "grandchild"
        return await self.session.process_utterance(self.session.sides[role], text)

    async def greet(self) -> None:
        """English for the grandchild, then the same line in the heritage language so the grandparent knows KIN joined."""
        g = self.session.translator.g
        await self.say(GREETING, "en")
        res = await asyncio.to_thread(self.session.translator.translate, GREETING, self.learner, self.grandparent,
                                      (), (), None, g.heritage_lang)
        if res.result.translation:
            await self.say(res.result.translation, g.heritage_lang)

    async def say(self, text: str, lang: str) -> None:
        async for chunk in self.session.tts.stream(text, voice_id="", language_code=lang):
            await self._play(chunk)

    async def _play(self, pcm16: bytes) -> None:
        out = to_twilio(pcm16)
        if out:
            await self.send_audio(out)


async def _ignore(_msg: dict) -> None:
    return None  # the phone legs have no screen; watchers (phone captions page) get the broadcast instead

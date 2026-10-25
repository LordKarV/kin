"""LiveWorld: the one object the call pipeline talks to (docs/ARCHITECTURE.md 8.5).

ponytail: STUB with the exact 8.5 signatures so the pipeline (3B) can code against it; task 3A replaces the bodies.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from ..mt.translate import Translator

Sends = dict[str, list[dict]]  # identity -> server->client messages


@dataclass(frozen=True)
class FinalResult:
    sends: Sends
    spans: list[dict]


class LiveWorld:
    def __init__(self, call_id: int, space_id: int, emit: Callable[[str, dict], Awaitable[None]],
                 loop: asyncio.AbstractEventLoop) -> None:
        self.call_id = call_id
        self.space_id = space_id
        self.emit = emit
        self.loop = loop

    def join(self, identity: str, person_id: int, lang: str) -> None:
        return None

    def leave(self, identity: str) -> None:
        return None

    def on_partial(self, speaker: str, text: str) -> Sends:
        return {}

    def on_final(self, speaker: str, text: str) -> FinalResult:
        return FinalResult({}, [])

    def on_translated(self, speaker: str, utterance_id: int, text: str, translations: dict[str, str],
                      audience: list[int]) -> Sends:
        return {}

    def asks(self, speaker: str, listeners: list[str], new_people: list) -> Sends:
        return {}

    def feedback(self, listener: str, key: str, action: str) -> None:
        return None

    def render(self, listener: str, node_id: str) -> str | None:
        return None

    def roster(self, listeners: list[str], speaker: str) -> str:
        return ""

    def translator(self, lang: str) -> "Translator":
        raise NotImplementedError("LiveWorld.translator lands in task 3A")

    def keyterms(self, speaker: str) -> list[str]:
        return []

    def refresh(self) -> None:
        return None

    def close(self) -> None:
        return None

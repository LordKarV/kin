"""Fade policy placeholder; the real BKT-driven policy lands in Phase 4. Until then: no passthrough."""
from __future__ import annotations

from typing import Callable


def make_fade_policy(family_id: int) -> Callable[[str, str], list[str]]:
    def policy(listener_slug: str, text: str) -> list[str]:
        return []
    return policy

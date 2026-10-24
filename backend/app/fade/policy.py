"""Fade policy used by the live pipeline: for the learner-listener direction, mastered heritage tokens pass through
untranslated. Guardrail (plan Phase 4): never inside a grounded entity span or a pragmatics-card span."""
from __future__ import annotations

import logging
from typing import Callable

from .service import passthrough_tokens

log = logging.getLogger("kin.fade")


def make_fade_policy(family_id: int) -> Callable[[str, str], list[str]]:
    def policy(listener_slug: str, text: str) -> list[str]:
        try:
            return passthrough_tokens(listener_slug, text, family_id)
        except Exception as e:  # noqa: BLE001  (never let Fade break a call)
            log.warning("fade policy failed: %s", e)
            return []
    return policy

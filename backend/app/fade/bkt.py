"""Bayesian Knowledge Tracing per (learner, lemma). Plan Phase 4: p_init=0.1, p_learn=0.2, p_slip=0.1, p_guess=0.2.
Two kinds of evidence, kept honest: an *exposure* (the word was heard with its translation) is a weak learning
opportunity with no observation; *verified understanding* (a 1-tap check or an appropriate reply) is a real observation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Params:
    p_init: float = 0.1
    p_learn: float = 0.2
    p_slip: float = 0.1
    p_guess: float = 0.2
    p_learn_exposure: float = 0.05   # weak: hearing a word with its translation


DEFAULT = Params()
MASTERY_THRESHOLD = 0.85


class BKT:
    def __init__(self, params: Params = DEFAULT):
        self.p = params

    def update(self, p_known: float, correct: bool) -> float:
        """Observation → posterior → learning transition."""
        s, g = self.p.p_slip, self.p.p_guess
        if correct:
            post = p_known * (1 - s) / (p_known * (1 - s) + (1 - p_known) * g)
        else:
            post = p_known * s / (p_known * s + (1 - p_known) * (1 - g))
        return min(1.0, post + (1 - post) * self.p.p_learn)

    def expose(self, p_known: float) -> float:
        """No observation, just a weak learning opportunity."""
        return min(1.0, p_known + (1 - p_known) * self.p.p_learn_exposure)

    def mastered(self, p_known: float) -> bool:
        return p_known >= MASTERY_THRESHOLD

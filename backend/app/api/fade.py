from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import get_settings
from ..fade import service

router = APIRouter(prefix="/api/fade", tags=["fade"])


class LearnerText(BaseModel):
    learner: str = "p_arjun"
    text: str = ""
    understood: bool = True
    utterance_id: int | None = None


class Sim(BaseModel):
    learner: str = "p_arjun"
    weeks: int = 1
    per_week: int = 3


@router.get("/mastery")
def mastery(learner: str = "p_arjun") -> list[dict]:
    return service.mastery(learner)


@router.post("/expose")
def expose(body: LearnerText) -> dict:
    return {"lemmas": service.record_exposures(body.learner, body.text)}


@router.post("/verify")
def verify(body: LearnerText) -> dict:
    return service.record_verification(body.model_dump())


@router.post("/policy")
def policy(body: LearnerText) -> dict:
    return {"passthrough": service.passthrough_tokens(body.learner, body.text, get_settings().demo_family_id)}


@router.post("/reset")
def reset(body: LearnerText) -> dict:
    return {"deleted": service.reset(body.learner)}


@router.post("/simulate")
def simulate(body: Sim) -> dict:
    return service.simulate(body.learner, body.weeks, body.per_week, get_settings().demo_family_id)

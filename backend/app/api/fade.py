from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..db.session import session_scope
from ..fade import service
from .calls import legacy_family

router = APIRouter(prefix="/api/fade", tags=["fade"])


class LearnerText(BaseModel):
    learner: str = "p_arjun"
    text: str = ""
    understood: bool = True
    utterance_id: int | None = None


def _family() -> int:
    """Fade is a legacy-family mode: the world space answers 404 like a missing family (D2), and every learner slug
    and utterance is looked up inside the sample family only."""
    with session_scope() as s:
        return legacy_family(s, None).id



@router.get("/mastery")
def mastery(learner: str = "p_arjun") -> list[dict]:
    return service.mastery(learner, _family())


@router.post("/expose")
def expose(body: LearnerText) -> dict:
    return {"lemmas": service.record_exposures(body.learner, body.text, family_id=_family())}


@router.post("/verify")
def verify(body: LearnerText) -> dict:
    return service.record_verification(body.model_dump(), _family())


@router.post("/policy")
def policy(body: LearnerText) -> dict:
    return {"passthrough": service.passthrough_tokens(body.learner, body.text, _family())}


@router.post("/reset")
def reset(body: LearnerText) -> dict:
    return {"deleted": service.reset(body.learner, _family())}

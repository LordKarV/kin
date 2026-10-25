"""Wire contracts for world calls (docs/ARCHITECTURE.md section 9) and the world LLM schemas (6.1, 7, 3.3, 8.5).

Server-to-client models mirror ios/Kin/Sources/Contracts/Contracts.swift; change both together.
LLM schemas are strict-mode shapes (llm.to_strict_schema): no defaults, comments instead of docstrings
(a docstring lands in the schema).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------------------------------------------------
# 9.1 server -> client (LiveKit data, topic "kin")


class ParticipantOut(BaseModel):
    identity: str
    person: str
    name: str
    lang: str


class PausedBy(BaseModel):
    person: str
    name: str


class KinState(BaseModel):
    on: bool
    paused_by: PausedBy | None = None


class SuggestionOut(BaseModel):
    owner: str
    relation: str
    label: str


class StateOut(BaseModel):
    label: str
    at: str  # "YYYY-MM-DD"
    known: bool = False


class GlanceItem(BaseModel):
    # Superset of the legacy glance item; old clients ignore unknown kinds. fact_ids never leave the server.
    key: str
    kind: Literal["who", "what", "term", "saying", "ask", "bridge", "storyline"]
    title: str = ""
    native: str = ""
    body: str = ""
    category: str = ""
    image_url: str = ""
    image_credit: str = ""
    source_url: str = ""
    node_id: str | None = None  # who/what
    gap: Literal["new", "reminder"] | None = None
    term: str = ""  # ask
    guess: str = ""
    suggestions: list[SuggestionOut] = []
    target: str | None = None  # bridge
    private: bool = False
    storyline_id: int | None = None  # storyline
    states: list[StateOut] = []


class JoinedMsg(BaseModel):
    type: Literal["joined"] = "joined"
    call_id: int
    identity: str
    person: str
    name: str
    lang: str
    role: str = "participant"
    peer_present: bool = False
    participants: list[ParticipantOut] = []
    kin: KinState


class ParticipantsMsg(BaseModel):
    type: Literal["participants"] = "participants"
    participants: list[ParticipantOut]


class KinStatusMsg(BaseModel):
    type: Literal["kin_status"] = "kin_status"
    on: bool
    paused_by: PausedBy | None = None


class PartialMsg(BaseModel):
    type: Literal["partial"] = "partial"
    speaker: str  # identity
    person: str
    role: str = "participant"
    lang: str
    text: str


class GlanceMsg(BaseModel):
    type: Literal["glance"] = "glance"
    speaker: str
    role: str = "participant"
    partial: bool = False
    items: list[GlanceItem]


class GlanceRetractMsg(BaseModel):
    type: Literal["glance_retract"] = "glance_retract"
    keys: list[str]


class GlanceUpdateMsg(BaseModel):
    type: Literal["glance_update"] = "glance_update"
    key: str
    body: str


class GroundedSpanOut(BaseModel):
    source: str
    rendered: str
    node_id: str | None = None  # null when the node is not visible to this listener (2.4)


class LinkerSpanOut(BaseModel):
    start: int
    end: int
    source: str
    node_id: str | None = None
    type: str
    confidence: float
    rendered: str = ""
    candidates: list[str] = []
    method: str = ""


class TranscriptMsg(BaseModel):
    type: Literal["transcript"] = "transcript"
    call_id: int
    utterance_id: int
    speaker: str  # person slug
    speaker_identity: str
    role: str = "participant"
    listener: str | None = None
    src_text: str
    src_lang: str
    src_lang_tags: list[str] = []
    target_lang: str
    heritage_lang: str = ""
    translation: str | None = None  # null when the listener shares the speaker's language
    grounded_spans: list[GroundedSpanOut] = []
    pragmatics_cards: list[dict] = []  # mt.schemas.PragmaticsCard JSON (not imported: mt.schemas imports this module)
    passthrough: list[str] = []
    confidence: float = 0.0
    linker_spans: list[LinkerSpanOut] = []
    latencies: dict[str, float] = {}
    error: str | None = None


class EnrichMsg(BaseModel):
    type: Literal["enrich"] = "enrich"
    utterance_id: int
    pragmatics_cards: list[dict] = []
    b_ms: float = 0.0


class AudioStartMsg(BaseModel):
    type: Literal["audio_start"] = "audio_start"
    utterance_id: int
    lang: str


class AudioEndMsg(BaseModel):
    type: Literal["audio_end"] = "audio_end"
    utterance_id: int


class LatencyMsg(BaseModel):
    type: Literal["latency"] = "latency"
    utterance_id: int
    latencies: dict[str, float]


class StatusMsg(BaseModel):
    type: Literal["status"] = "status"
    asr: Literal["ok", "unavailable", "ended"]
    detail: str = ""


class ErrorMsg(BaseModel):
    type: Literal["error"] = "error"
    stage: Literal["mt", "tts", "pipeline"]
    message: str = ""


ServerMsg = (JoinedMsg | ParticipantsMsg | KinStatusMsg | PartialMsg | GlanceMsg | GlanceRetractMsg | GlanceUpdateMsg
             | TranscriptMsg | EnrichMsg | AudioStartMsg | AudioEndMsg | LatencyMsg | StatusMsg | ErrorMsg)

# ---------------------------------------------------------------------------------------------------------------------
# 9.2 REST bodies

Circle = Literal["family", "friends", "group"]


class UserIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    lang: str = Field(min_length=2, max_length=8)
    phone: str | None = None


class UserOut(BaseModel):
    user_id: int
    person_id: int
    person: str
    space_id: int
    token: str  # shown once
    sms_number: str = ""


class MeOut(BaseModel):
    user_id: int
    person_id: int
    person: str
    name: str
    lang: str
    phone: str | None = None


class MePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    lang: str | None = Field(default=None, min_length=2, max_length=8)
    phone: str | None = None


class DeleteMeOut(BaseModel):
    deleted: bool = True
    facts: int
    utterances: int


class ContactOut(BaseModel):
    person: str
    name: str
    lang: str
    render: str
    circle: Circle


class WorldPersonOut(BaseModel):
    id: int
    person: str
    name: str
    render: str
    lang: str = ""
    is_user: bool
    circle: Circle | None = None


class WorldTieOut(BaseModel):
    src: str
    dst: str
    kind: str
    context: str = ""


class WorldEdgeOut(BaseModel):
    src: str
    dst: str
    relation: str


class WorldGroupOut(BaseModel):
    id: int
    name: str
    members: list[str]


class WorldThingOut(BaseModel):
    id: int
    slug: str
    kind: str
    name: str
    owner: str | None = None


class WorldStateOut(BaseModel):
    label: str
    at: str


class WorldStorylineOut(BaseModel):
    id: int
    title: str
    status: str
    states: list[WorldStateOut] = []
    owner: str | None = None  # person slug; None when the owner is not visible to the viewer


class WorldOut(BaseModel):
    me: str  # my person slug
    people: list[WorldPersonOut] = []
    ties: list[WorldTieOut] = []
    edges: list[WorldEdgeOut] = []
    groups: list[WorldGroupOut] = []
    things: list[WorldThingOut] = []
    storylines: list[WorldStorylineOut] = []


class SocialRelationOut(BaseModel):
    kind: str
    label: str


class KinRelationOut(BaseModel):
    path: str
    label: str


class RelationsOut(BaseModel):
    social: list[SocialRelationOut] = []
    kin: list[KinRelationOut] = []


class PlaceIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    person: str | None = None  # existing slug
    owner: str
    relation: str
    context: str | None = Field(default=None, max_length=160)
    call_id: int | None = None


class PlaceOut(BaseModel):
    id: int
    person: str
    name: str
    render: str


class HeardByOut(BaseModel):
    person: str
    name: str
    via: str


class FactRow(BaseModel):  # REST "Fact"; FactOut is the extraction schema below
    id: int
    text: str
    subject: str
    speaker: str | None = None
    source_kind: str
    said_at: datetime
    status: str
    sensitive_kind: str = ""
    pinned: bool = False
    expires_at: datetime | None = None
    heard_by: list[HeardByOut] = []


class FactsOut(BaseModel):
    about_me: list[FactRow] = []
    i_said: list[FactRow] = []


class FactPatch(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=400)
    status: Literal["active", "resolved", "contradicted", "superseded"] | None = None
    pinned: bool | None = None
    remembered: bool | None = None


class DeletedOut(BaseModel):
    deleted: bool = True


class DeletePersonOut(BaseModel):
    deleted_facts: int
    person_deleted: bool


class PauseIn(BaseModel):
    paused: bool


class PauseOut(BaseModel):
    on: bool
    paused_by: PausedBy | None = None


class FeedbackIn(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    action: Literal["know", "dismiss", "remember"]


class OkOut(BaseModel):
    ok: bool = True


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class CallParticipantOut(BaseModel):
    person: str
    identity: str
    lang: str
    joined_at: datetime
    left_at: datetime | None = None


class RtcJoinWorldIn(BaseModel):
    call_id: int | None = None
    invite: str | None = None  # required for a new seat in an existing call; a held seat rejoins without it


class JoinWorldOut(BaseModel):
    call_id: int
    room: str
    token: str
    url: str
    identity: str
    person: str
    name: str
    lang: str
    invite: str = ""  # this call's invite code, for the share link
    participants: list[ParticipantOut] = []


class DevSmsIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field(alias="from")
    body: str

    @field_validator("body")
    @classmethod
    def _truncate(cls, v: str) -> str:
        return v[:1600]  # section 7: long bodies are truncated, not rejected, same as the Twilio path


class FactBrief(BaseModel):
    id: int
    text: str


class DevSmsOut(BaseModel):
    reply: str
    message_id: int | None = None
    facts: list[FactBrief] = []


class ClockIn(BaseModel):
    offset_days: float


class ClockOut(BaseModel):
    now: datetime


class AppliedEntity(BaseModel):
    ref: str
    id: int
    slug: str


class DevApplyOut(BaseModel):
    facts: list[int] = []
    entities: list[AppliedEntity] = []


# ---------------------------------------------------------------------------------------------------------------------
# LLM schemas (strict: every key required; "" / null / [] for none)

SensitiveKind = Literal["", "health", "money", "conflict"]


class EntityOut(BaseModel):
    ref: str
    name: str
    native: str
    forms: list[str]
    kind: Literal["person", "place", "event", "thing", "group"]
    existing_id: int | None


class TieOut(BaseModel):
    a: str  # ref | "speaker" | existing slug
    b: str
    kind: str
    context: str


class StoryOut(BaseModel):
    existing_id: int | None
    title: str
    state_label: str
    resolved: bool


class FactOut(BaseModel):
    subject: str
    predicate: str
    text_en: str
    text_src: str
    keys: list[list[str]]
    refs: list[str]
    lines: list[int]
    sensitive_kind: SensitiveKind
    same_as: int | None
    contradicts: int | None
    storyline: StoryOut | None


class WorldUpdateOut(BaseModel):
    entities: list[EntityOut]
    ties: list[TieOut]
    facts: list[FactOut]


class SmsFact(BaseModel):
    predicate: str
    text_en: str
    keys: list[list[str]]
    sensitive_kind: SensitiveKind
    storyline: StoryOut | None
    told: list[str]  # names the author says already know


class SmsOut(BaseModel):
    facts: list[SmsFact]
    ack: str  # <= 120 chars, restates the news, no advice


class FormItem(BaseModel):
    lang: str
    form: str


class FormsOut(BaseModel):
    forms: list[FormItem]


class LocalizeItem(BaseModel):
    key: str
    body: str


class LocalizeOut(BaseModel):
    items: list[LocalizeItem]


class NewPerson(BaseModel):  # CardsOut.new_people item (call B)
    source: str
    name: str
    owner: Literal["speaker", "listener", "other"]
    owner_name: str
    relation: str
    context: str


class BridgeOut(BaseModel):  # optional rerank (section 5), off by default
    fact_id: int | None


class DevApplyIn(BaseModel):
    call_id: int | None = None
    speaker: str
    audience: list[str] = []
    update: WorldUpdateOut

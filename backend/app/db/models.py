"""KIN data model (plan §7). Graph is relational: Person nodes + Edge rows. SQLite or Postgres."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """DateTime(timezone=True) that reads back aware. SQLite drops tzinfo, and world code compares against clock.now()."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


class Family(Base):
    __tablename__ = "families"
    # One world space: get_space relies on this to survive two concurrent first sign-ups.
    __table_args__ = (Index("uq_one_space", "kind", unique=True, sqlite_where=text("kind = 'space'"),
                            postgresql_where=text("kind = 'space'")),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    heritage_lang: Mapped[str] = mapped_column(String(8))  # ISO 639-1 code
    kind: Mapped[str] = mapped_column(String(8), default="family")  # family | space (the one world space)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    people: Mapped[list["Person"]] = relationship(back_populates="family", cascade="all, delete-orphan")


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (UniqueConstraint("family_id", "slug"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    slug: Mapped[str] = mapped_column(String(64))  # stable id used by eval + UI, e.g. p_ravi_mama
    display_name: Mapped[str] = mapped_column(String(120))  # English/romanized
    lang_name: Mapped[str] = mapped_column(String(120), default="")  # heritage-script name
    gender: Mapped[str] = mapped_column(String(1), default="?")  # m | f | ?
    birth_year_approx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_learner: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deceased: Mapped[bool] = mapped_column(Boolean, default=False)
    voice_id: Mapped[str] = mapped_column(String(80), default="")  # TTS voice (clone only with consent)
    cues: Mapped[list] = mapped_column(JSON, default=list)  # topic/place words that hint at this person (both scripts)

    family: Mapped[Family] = relationship(back_populates="people")
    aliases: Mapped[list["Alias"]] = relationship(back_populates="person", cascade="all, delete-orphan")


class Alias(Base):
    __tablename__ = "aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    alias: Mapped[str] = mapped_column(String(120))
    lang: Mapped[str] = mapped_column(String(8), default="en")
    kind: Mapped[str] = mapped_column(String(24), default="name")  # name | nickname | script | address

    person: Mapped[Person] = relationship(back_populates="aliases")


class Edge(Base):
    """Directed kinship edge. relation ∈ {parent, spouse, sibling}.
    parent: src is parent of dst. sibling: meta {"src_is_elder": bool}. lang_term: how dst addresses src in the family."""
    __tablename__ = "edges"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    src_person: Mapped[int] = mapped_column(ForeignKey("people.id"))
    dst_person: Mapped[int] = mapped_column(ForeignKey("people.id"))
    relation: Mapped[str] = mapped_column(String(24))
    lang_term: Mapped[str] = mapped_column(String(64), default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    fact_id: Mapped[int | None] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), nullable=True)  # NULL = legacy/setup


class Thing(Base):
    __tablename__ = "things"
    __table_args__ = (UniqueConstraint("family_id", "slug"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    slug: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))  # dish | place | event
    name: Mapped[str] = mapped_column(String(120))
    lang_name: Mapped[str] = mapped_column(String(120), default="")
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")  # the family-specific meaning
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), nullable=True)  # whose world
    fact_id: Mapped[int | None] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), nullable=True)
    keys: Mapped[list] = mapped_column(JSON, default=list)  # concept groups: list[list[str]]


class Language(Base):
    """One row per supported heritage language: the full kin table + morphology, as seeded from app/graph/kin_tables."""
    __tablename__ = "languages"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    native_name: Mapped[str] = mapped_column(String(64), default="")
    locale: Mapped[str] = mapped_column(String(12), default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(40), default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # the table JSON (morphology + terms)


class KinTerm(Base):
    __tablename__ = "kin_terms"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int | None] = mapped_column(ForeignKey("families.id"), nullable=True)  # None = language default
    lang: Mapped[str] = mapped_column(String(8))
    term: Mapped[str] = mapped_column(String(64))
    script_form: Mapped[str] = mapped_column(String(64), default="")
    kind: Mapped[str] = mapped_column(String(16), default="kin")  # kin | endearment | honorific
    relation_patterns: Mapped[list] = mapped_column(JSON, default=list)
    variants: Mapped[list] = mapped_column(JSON, default=list)
    gloss: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class Call(Base):
    __tablename__ = "calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    participants: Mapped[list] = mapped_column(JSON, default=list)  # person ids
    transport: Mapped[str] = mapped_column(String(16), default="websocket")
    mode: Mapped[str] = mapped_column(String(8), default="legacy")  # legacy | world


class Utterance(Base):
    __tablename__ = "utterances"
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"))
    speaker_id: Mapped[int | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    listener_id: Mapped[int | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    t_start: Mapped[float] = mapped_column(Float, default=0.0)
    t_end: Mapped[float] = mapped_column(Float, default=0.0)
    src_text: Mapped[str] = mapped_column(Text)
    src_lang_tags: Mapped[list] = mapped_column(JSON, default=list)
    translation: Mapped[str] = mapped_column(Text, default="")
    grounded_spans: Mapped[list] = mapped_column(JSON, default=list)
    cards: Mapped[list] = mapped_column(JSON, default=list)
    passthrough: Mapped[list] = mapped_column(JSON, default=list)
    audio_url: Mapped[str] = mapped_column(String(300), default="")
    latencies: Mapped[dict] = mapped_column(JSON, default=dict)  # ms per stage
    sensitive_topic: Mapped[str] = mapped_column(String(80), default="")  # health|money|conflict topic word; text withheld unless remembered
    lang: Mapped[str] = mapped_column(String(8), default="")
    audience: Mapped[list] = mapped_column(JSON, default=list)  # person ids present and not paused, speaker excluded
    translations: Mapped[dict] = mapped_column(JSON, default=dict)  # {lang: text}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GlossaryEntry(Base):
    __tablename__ = "glossary"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    card: Mapped[dict] = mapped_column(JSON)
    utterance_id: Mapped[int | None] = mapped_column(ForeignKey("utterances.id"), nullable=True)
    speaker_id: Mapped[int | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    audio_url: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Mastery(Base):
    __tablename__ = "mastery"
    __table_args__ = (UniqueConstraint("learner_id", "lemma"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    lemma: Mapped[str] = mapped_column(String(120))
    p_known: Mapped[float] = mapped_column(Float, default=0.1)
    n_exposures: Mapped[int] = mapped_column(Integer, default=0)
    n_verified: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), unique=True)
    voice_clone: Mapped[bool] = mapped_column(Boolean, default=False)
    memory: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- common-ground world (docs/ARCHITECTURE.md section 1.2). family_id here means space id. ---

def _people_fk(nullable: bool = False, set_null: bool = False):
    return mapped_column(ForeignKey("people.id", ondelete="SET NULL" if set_null else "CASCADE"), nullable=nullable)


class User(Base):
    """A Person who has the app."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), unique=True)
    lang: Mapped[str] = mapped_column(String(8))  # a MUSE_LANGUAGES code
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)  # E.164
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 hex of the X-KIN-User token
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("family_id", "slug"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    lang_name: Mapped[str] = mapped_column(String(120), default="")
    fact_id: Mapped[int | None] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), nullable=True)


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "person_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    person_id: Mapped[int] = _people_fk()
    fact_id: Mapped[int | None] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), nullable=True)


class Tie(Base):
    """Social relation: dst is src's <kind>."""
    __tablename__ = "ties"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    src_person: Mapped[int] = _people_fk()  # owner side: Mei in "Mei's friend Lin"
    dst_person: Mapped[int] = _people_fk()
    kind: Mapped[str] = mapped_column(String(16))  # friend|close_friend|partner|roommate|classmate|coworker|teammate|knows
    context: Mapped[str] = mapped_column(String(160), default="")  # English
    status: Mapped[str] = mapped_column(String(8), default="active")  # active|ended
    fact_id: Mapped[int | None] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), nullable=True)  # NULL only for setup
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class Fact(Base):
    __tablename__ = "facts"
    __table_args__ = (Index("ix_facts_subject_id", "subject_id"), Index("ix_facts_expires_at", "expires_at"))
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    subject_id: Mapped[int] = _people_fk()  # whose fact it is
    speaker_id: Mapped[int | None] = _people_fk(nullable=True, set_null=True)  # who said/texted/tapped it
    predicate: Mapped[str] = mapped_column(String(16))  # tie|lives_in|from|works_at|studies_at|did|started|plans|state|attribute|mention
    text: Mapped[str] = mapped_column(String(400))  # short canonical English
    text_src: Mapped[str] = mapped_column(String(400), default="")  # original-language span ("" when sensitive)
    lang: Mapped[str] = mapped_column(String(8))
    keys: Mapped[list] = mapped_column(JSON, default=list)  # concept groups: list[list[str]]
    source_kind: Mapped[str] = mapped_column(String(8))  # call|message|card|setup
    call_id: Mapped[int | None] = mapped_column(ForeignKey("calls.id", ondelete="SET NULL"), nullable=True)
    utterance_id: Mapped[int | None] = mapped_column(ForeignKey("utterances.id", ondelete="SET NULL"), nullable=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    said_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(12), default="active")  # active|resolved|contradicted|superseded
    superseded_by: Mapped[int | None] = mapped_column(ForeignKey("facts.id", ondelete="SET NULL"), nullable=True)
    storyline_id: Mapped[int | None] = mapped_column(ForeignKey("storylines.id", ondelete="CASCADE"), nullable=True)
    sensitive_kind: Mapped[str] = mapped_column(String(8), default="")  # ""|health|money|conflict
    remembered: Mapped[bool] = mapped_column(Boolean, default=False)
    shareable: Mapped[bool] = mapped_column(Boolean, default=True)  # False for SMS facts
    third_party: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)


class FactAudience(Base):
    """Who has heard a fact: visibility and disclosure in one table."""
    __tablename__ = "fact_audience"
    __table_args__ = (UniqueConstraint("fact_id", "person_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    fact_id: Mapped[int] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"))
    person_id: Mapped[int] = _people_fk()
    via: Mapped[str] = mapped_column(String(8))  # said|heard|authored|told|card
    at: Mapped[datetime] = mapped_column(UTCDateTime)
    call_id: Mapped[int | None] = mapped_column(ForeignKey("calls.id", ondelete="SET NULL"), nullable=True)


class FactRef(Base):
    """Entities a fact mentions."""
    __tablename__ = "fact_refs"
    __table_args__ = (Index("ix_fact_refs_kind_ref_id", "kind", "ref_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    fact_id: Mapped[int] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))  # person|thing|group
    ref_id: Mapped[int] = mapped_column(Integer)


class Storyline(Base):
    __tablename__ = "storylines"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    slug: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[int] = _people_fk()  # whose thread
    title: Mapped[str] = mapped_column(String(120))
    keys: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(8), default="open")  # open|resolved
    unresolved: Mapped[bool] = mapped_column(Boolean, default=False)  # contradiction flag
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class StorylineState(Base):
    __tablename__ = "storyline_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    storyline_id: Mapped[int] = mapped_column(ForeignKey("storylines.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(80))
    fact_id: Mapped[int] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"))  # provenance and visibility
    at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(12), default="active")  # active|superseded|contradicted


class Knowledge(Base):
    """Common-ground state, one row per (knower, item)."""
    __tablename__ = "knowledge"
    __table_args__ = (UniqueConstraint("knower_id", "item_kind", "item_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    knower_id: Mapped[int] = _people_fk()
    item_kind: Mapped[str] = mapped_column(String(8))  # person|thing|group|fact|state
    item_id: Mapped[int] = mapped_column(Integer)
    p: Mapped[float] = mapped_column(Float)  # P(knows) at last_at
    half_life_days: Mapped[float] = mapped_column(Float)
    first_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_day: Mapped[str] = mapped_column(String(10))  # "YYYY-MM-DD" UTC of last evidence
    n_heard: Mapped[int] = mapped_column(Integer, default=0)
    n_shown: Mapped[int] = mapped_column(Integer, default=0)
    n_said: Mapped[int] = mapped_column(Integer, default=0)
    n_confirmed: Mapped[int] = mapped_column(Integer, default=0)
    n_asked: Mapped[int] = mapped_column(Integer, default=0)


class CardLog(Base):
    """What was delivered: rate limits, bridge "not again", eval, delete scans."""
    __tablename__ = "card_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    listener_id: Mapped[int] = _people_fk()
    target_id: Mapped[int | None] = _people_fk(nullable=True, set_null=True)  # bridges: who has not heard it
    kind: Mapped[str] = mapped_column(String(10))
    key: Mapped[str] = mapped_column(String(80))
    fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    at: Mapped[datetime] = mapped_column(UTCDateTime)
    final: Mapped[bool] = mapped_column(Boolean, default=False)
    retracted: Mapped[bool] = mapped_column(Boolean, default=False)


class Message(Base):
    """SMS, private to the author."""
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    author_id: Mapped[int] = _people_fk()
    body: Mapped[str] = mapped_column(Text, default="")  # cleared after a successful parse
    from_number: Mapped[str] = mapped_column(String(20))
    provider_sid: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)  # idempotency key for a resent message
    received_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(8), default="received")  # received|parsed|failed
    reply: Mapped[str] = mapped_column(String(200), default="")
    error: Mapped[str] = mapped_column(String(200), default="")
    fact_ids: Mapped[list] = mapped_column(JSON, default=list)


class CallParticipant(Base):
    __tablename__ = "call_participants"
    __table_args__ = (UniqueConstraint("call_id", "person_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    person_id: Mapped[int] = _people_fk()
    identity: Mapped[str] = mapped_column(String(64))  # "p<person_id>"
    lang: Mapped[str] = mapped_column(String(8))
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime)
    left_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

"""KIN data model (plan §7). Graph is relational: Person nodes + Edge rows. SQLite or Postgres."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Family(Base):
    __tablename__ = "families"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    heritage_lang: Mapped[str] = mapped_column(String(8))  # ISO 639-1, e.g. "ta"
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
    lang: Mapped[str] = mapped_column(String(8), default="ta")
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


class KinTerm(Base):
    __tablename__ = "kin_terms"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int | None] = mapped_column(ForeignKey("families.id"), nullable=True)  # None = language default
    lang: Mapped[str] = mapped_column(String(8))
    term: Mapped[str] = mapped_column(String(64))
    script_form: Mapped[str] = mapped_column(String(64), default="")
    kind: Mapped[str] = mapped_column(String(16), default="kin")  # kin | endearment | honorific
    relation_patterns: Mapped[list] = mapped_column(JSON, default=list)
    gloss: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class Call(Base):
    __tablename__ = "calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    participants: Mapped[list] = mapped_column(JSON, default=list)  # person ids
    transport: Mapped[str] = mapped_column(String(16), default="websocket")


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


class CallSummary(Base):
    __tablename__ = "call_summaries"
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), unique=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), unique=True)
    voice_clone: Mapped[bool] = mapped_column(Boolean, default=False)
    memory: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

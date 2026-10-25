"""World space and user helpers (docs/ARCHITECTURE.md section 1.2). Pure DB helpers, no HTTP."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import models as m
from ..graph.kin_tables import MUSE_LANGUAGES

SPACE_NAME = "KIN space"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _fold(name: str) -> str:
    base = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:24].strip("_")


def get_space(s: Session, lang: str = "en") -> m.Family:
    """The one world space; created lazily with the creating user's language as heritage_lang."""
    q = select(m.Family).where(m.Family.kind == "space").order_by(m.Family.id).limit(1)
    space = s.scalars(q).first()
    if space is not None:
        return space
    try:
        with s.begin_nested():  # uq_one_space: a concurrent first sign-up may win the insert
            space = m.Family(name=SPACE_NAME, heritage_lang=lang, kind="space")
            s.add(space)
        return space
    except IntegrityError:
        return s.scalars(q).one()


def create_user(s: Session, name: str, lang: str, phone: str | None = None) -> tuple[m.User, m.Person, str]:
    """Create a canonical Person plus its User. Returns the raw token once; only its sha256 is stored."""
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    if lang not in MUSE_LANGUAGES:
        raise ValueError(f"unsupported language {lang!r}; expected one of {sorted(MUSE_LANGUAGES)}")
    norm_phone = None
    if phone is not None:
        norm_phone = normalize_phone(phone)
        if norm_phone is None:
            raise ValueError(f"invalid phone number {phone!r}")
        if s.scalar(select(m.User.id).where(m.User.phone == norm_phone)) is not None:
            raise ValueError("phone already linked")  # the unique constraint stays as the race backstop
    space = get_space(s, lang)
    # Slug needs the id, so insert with a unique placeholder and rename after flush.
    person = m.Person(family_id=space.id, slug=f"tmp_{secrets.token_hex(8)}", display_name=name)
    s.add(person)
    s.flush()
    folded = _fold(name)
    person.slug = f"p_{folded}_{person.id}" if folded else f"p_{person.id}"
    token = secrets.token_urlsafe(32)
    user = m.User(person_id=person.id, lang=lang, phone=norm_phone, token_hash=_hash(token))
    s.add(user)
    s.flush()
    return user, person, token


def user_by_token(s: Session, token: str | None) -> m.User | None:
    if not token:
        return None
    return s.scalars(select(m.User).where(m.User.token_hash == _hash(token))).first()


def phone_code(user: m.User) -> str:
    """The code a user texts ("KIN <code>") to link the number they text from. Keyed by the token hash, which never
    leaves the server, so only the signed-in user (GET /api/me/phone-code) can learn it."""
    return hmac.new(user.token_hash.encode(), b"kin-phone-link", hashlib.sha256).hexdigest()[:6]


def link_phone(s: Session, phone: str, code: str) -> m.User | None:
    """Give `phone` to the unlinked user whose phone_code is `code`; None when no one matches.
    ponytail: scans unlinked users (one HMAC each); store the code in a column if users reach the thousands."""
    code = code.strip().lower()
    for user in s.scalars(select(m.User).where(m.User.phone.is_(None))):
        if hmac.compare_digest(phone_code(user), code):
            user.phone = phone
            s.flush()
            return user
    return None


def normalize_phone(raw: str | None) -> str | None:
    """E.164 '+<digits>' (8-15 digits) or None, so a typed number matches Twilio's From.
    Any Unicode decimal digit counts (other scripts' digits, fullwidth)."""
    if not raw:
        return None
    digits = "".join(str(unicodedata.digit(c)) for c in raw if c.isdecimal())
    if len(digits) == 10 and not raw.strip().startswith("+"):
        digits = "1" + digits  # ponytail: bare 10 digits = US; add a country picker if non-US users type local numbers
    if not 8 <= len(digits) <= 15:
        return None
    return "+" + digits

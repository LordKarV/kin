"""Wikipedia picture + one-line description for a glance card. Never on the hot path.

Endpoint VERIFIED live 2026-10-24: GET https://en.wikipedia.org/api/rest_v1/page/summary/{title} returns JSON with
title, extract, thumbnail{source,width,height}, originalimage, content_urls.desktop.page; 404 for a missing page.
Wikimedia's User-Agent policy asks for a descriptive UA with contact info.

First sighting: `cached()` misses, the caller schedules `fetch()` in a thread; later sightings are a dict lookup.
Results (including misses) persist in backend/media/pictures/cache.json (gitignored).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import httpx

log = logging.getLogger("kin.cards.images")
SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
USER_AGENT = os.environ.get("WIKI_USER_AGENT", "KIN-family-interpreter/0.1 (HackTX 2026 hackathon demo; python-httpx)")  # add a contact via env
TIMEOUT_S = 6.0
MISS_TTL_S = 24 * 3600  # retry a failed/missing title after a day
CACHE_PATH = Path(__file__).resolve().parents[2] / "media" / "pictures" / "cache.json"

Fetcher = Callable[[str], dict | None]


def first_sentence(s: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", s.strip())
    return (m.group(1) if m else s.strip())[:300]


def fetch_summary(title: str) -> dict | None:
    """One REST call. Returns a picture record, or None for a missing page. Raises httpx errors on network failure."""
    url = SUMMARY_URL.format(title=quote(title.replace(" ", "_"), safe=""))
    r = httpx.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=TIMEOUT_S, follow_redirects=True)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    j = r.json()
    if j.get("type") == "disambiguation":
        return None
    page = ((j.get("content_urls") or {}).get("desktop") or {}).get("page", "")
    return {"title": j.get("title", title), "extract": first_sentence(j.get("extract", "")),
            "image_url": (j.get("thumbnail") or {}).get("source", ""), "source_url": page,
            "image_credit": f"Wikipedia: {j.get('title', title)} (text CC BY-SA; image via Wikimedia Commons, see page)"}


class Pictures:
    def __init__(self, path: Path = CACHE_PATH, fetcher: Fetcher = fetch_summary):
        self.path = path
        self.fetcher = fetcher
        self._lock = threading.Lock()
        self._inflight: set[str] = set()
        try:
            self._cache: dict[str, dict] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError) as e:
            log.warning("picture cache unreadable (%s); starting empty", e)
            self._cache = {}

    def cached(self, title: str) -> dict | None:
        """Instant: the record if we have a picture for this title, else None."""
        rec = self._cache.get(title)
        return rec if rec and rec.get("ok") else None

    def needs_fetch(self, title: str) -> bool:
        rec = self._cache.get(title)
        if rec is None:
            return title not in self._inflight
        return not rec.get("ok") and time.time() - rec.get("at", 0) > MISS_TTL_S and title not in self._inflight

    def fetch(self, title: str) -> dict | None:
        """Blocking: call from a worker thread. Records misses so they are not refetched every sighting."""
        with self._lock:
            if title in self._inflight:
                return None
            self._inflight.add(title)
        try:
            rec = self.fetcher(title)
            ok = bool(rec and rec.get("image_url"))
            entry = {**(rec or {}), "ok": ok, "at": time.time()}
        except (httpx.HTTPError, ValueError) as e:
            log.info("wikipedia summary failed for %r: %s", title, e)
            entry = {"ok": False, "at": time.time(), "error": str(e)[:120]}
        finally:
            with self._lock:
                self._inflight.discard(title)
        with self._lock:
            self._cache = {**self._cache, title: entry}
            self._save()
        return entry if entry["ok"] else None

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._cache, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as e:
            log.warning("picture cache not saved: %s", e)


_pictures: Pictures | None = None


def get_pictures() -> Pictures:
    global _pictures
    if _pictures is None:
        _pictures = Pictures()
    return _pictures


def set_pictures(p: Pictures | None) -> None:
    """Tests inject a Pictures with a fake fetcher and a tmp path."""
    global _pictures
    _pictures = p

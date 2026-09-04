"""Human-readable, deterministic clip filenames (no random UUIDs)."""

from __future__ import annotations

import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_CATEGORY_SLUG = {
    "story": "story",
    "lesson": "lesson",
    "insight": "insight",
    "surprising insight": "insight",
    "advice": "advice",
    "opinion": "opinion",
    "question": "question",
    "statistic": "stat",
    "emotional": "moment",
    "contrarian": "hot-take",
    "how-to": "how-to",
    "definition": "explainer",
}


def clip_slug(text: str, *, max_len: int = 40) -> str:
    s = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rsplit("-", 1)[0]
    return s or "clip"


def clip_filename(index: int, category: str, hook: str, *, top: bool = False) -> str:
    n = f"{index:02d}"
    if top:
        return f"{n}_highest-potential.mp4"
    cat = _CATEGORY_SLUG.get((category or "").lower(), clip_slug(category or "clip", max_len=16))
    tail = clip_slug(hook, max_len=32)
    if tail and tail != "clip":
        return f"{n}_{cat}_{tail}.mp4"
    return f"{n}_{cat}.mp4"

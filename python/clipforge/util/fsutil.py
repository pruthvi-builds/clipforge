"""Filesystem helpers: filename sanitising, safe join, atomic JSON."""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
import uuid
from pathlib import Path
from typing import Any

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_MULTI_DASH = re.compile(r"-{2,}")

SUPPORTED_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def sanitize_filename(name: str, *, default: str = "video") -> str:
    """Return a filesystem- and shell-safe base filename.

    Strips directory components, normalises unicode, removes anything that is not
    ``[A-Za-z0-9._-]`` and collapses dashes. Never returns an empty string and
    never returns a name that starts with a dot or a dash.
    """
    name = os.path.basename(name or "")
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    stem, ext = os.path.splitext(name)
    ext = _SAFE_CHARS.sub("", ext.lower())
    stem = _SAFE_CHARS.sub("-", stem).strip("-._")
    stem = _MULTI_DASH.sub("-", stem)
    if not stem:
        stem = default
    stem = stem[:80]
    if ext and not ext.startswith("."):
        ext = "." + ext
    return f"{stem}{ext}" if ext else stem


def new_project_id() -> str:
    return uuid.uuid4().hex[:12]


def safe_join(base: Path, *parts: str) -> Path:
    """Join ``parts`` onto ``base`` and refuse to escape ``base``."""
    base = Path(base).resolve()
    target = base
    for p in parts:
        target = target / p
    target = target.resolve()
    if base != target and base not in target.parents:
        raise ValueError(f"Unsafe path outside project directory: {target}")
    return target


def ensure_project_tree(project_dir: Path) -> dict[str, Path]:
    """Create the standard on-disk layout for a project and return the paths."""
    project_dir = Path(project_dir)
    tree = {
        "root": project_dir,
        "clips": project_dir / "clips",
        "renders": project_dir / "renders",
        "thumbnails": project_dir / "thumbnails",
        "frames": project_dir / "frames",
    }
    for p in tree.values():
        p.mkdir(parents=True, exist_ok=True)
    return tree


def write_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path: Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)

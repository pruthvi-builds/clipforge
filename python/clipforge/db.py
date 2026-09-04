"""SQLite persistence layer (stdlib ``sqlite3`` — no ORM needed for this size).

Tables: projects, videos, transcripts, clips, jobs, settings.
Large blobs (transcript segments, analysis) live on disk under the project dir;
the DB stores paths + summary rows so the dashboard is fast.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'created',
    style         TEXT DEFAULT 'general',
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    error         TEXT
);

CREATE TABLE IF NOT EXISTS videos (
    project_id     TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    filename       TEXT NOT NULL,
    path           TEXT NOT NULL,
    duration       REAL,
    width          INTEGER,
    height         INTEGER,
    fps            REAL,
    has_audio      INTEGER,
    size_bytes     INTEGER,
    meta_json      TEXT
);

CREATE TABLE IF NOT EXISTS transcripts (
    project_id     TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    language       TEXT,
    backend        TEXT,
    model          TEXT,
    has_word_ts    INTEGER,
    n_segments     INTEGER,
    path           TEXT
);

CREATE TABLE IF NOT EXISTS clips (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    idx            INTEGER NOT NULL,
    start          REAL NOT NULL,
    end            REAL NOT NULL,
    duration       REAL NOT NULL,
    category       TEXT,
    hook           TEXT,
    alt_hook       TEXT,
    opening_text   TEXT,
    reason         TEXT,
    self_contained INTEGER,
    score_overall  INTEGER,
    score_json     TEXT,
    text           TEXT,
    emphasis_json  TEXT,
    llm_used       INTEGER,
    render_path    TEXT,
    srt_path       TEXT,
    ass_path       TEXT,
    thumb_path     TEXT,
    render_status  TEXT DEFAULT 'pending',
    updated_at     REAL
);
CREATE INDEX IF NOT EXISTS idx_clips_project ON clips(project_id, idx);

CREATE TABLE IF NOT EXISTS jobs (
    id             TEXT PRIMARY KEY,
    project_id     TEXT REFERENCES projects(id) ON DELETE CASCADE,
    kind           TEXT NOT NULL,
    state          TEXT NOT NULL DEFAULT 'queued',
    priority       INTEGER NOT NULL DEFAULT 0,
    params_json    TEXT,
    stage          TEXT,
    progress       REAL DEFAULT 0,
    message        TEXT,
    error          TEXT,
    created_at     REAL NOT NULL,
    started_at     REAL,
    finished_at    REAL,
    attempts       INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state, priority DESC, created_at);

CREATE TABLE IF NOT EXISTS settings (
    key            TEXT PRIMARY KEY,
    value          TEXT
);
"""


def db_path() -> Path:
    return get_settings().db_path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as c:
        c.executescript(_SCHEMA)


def now() -> float:
    return time.time()


# ---------------------------------------------------------------- projects
def create_project(pid: str, name: str, style: str = "general") -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO projects (id, name, status, style, created_at, updated_at) "
            "VALUES (?, ?, 'created', ?, ?, ?)",
            (pid, name, style, now(), now()),
        )


def set_project_status(pid: str, status: str, error: str | None = None) -> None:
    with connect() as c:
        c.execute(
            "UPDATE projects SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, error, now(), pid),
        )


def get_project(pid: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        if not row:
            return None
        proj = dict(row)
        v = c.execute("SELECT * FROM videos WHERE project_id = ?", (pid,)).fetchone()
        t = c.execute("SELECT * FROM transcripts WHERE project_id = ?", (pid,)).fetchone()
        clips = c.execute(
            "SELECT * FROM clips WHERE project_id = ? ORDER BY idx", (pid,)
        ).fetchall()
        proj["video"] = dict(v) if v else None
        proj["transcript"] = dict(t) if t else None
        proj["clips"] = [_clip_row_to_dict(dict(r)) for r in clips]
        return proj


def list_projects(limit: int = 100) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            """
            SELECT p.*, v.filename, v.duration, v.width, v.height, v.path AS video_path,
                   (SELECT COUNT(*) FROM clips WHERE project_id = p.id) AS n_clips
            FROM projects p LEFT JOIN videos v ON v.project_id = p.id
            ORDER BY p.created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_project(pid: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM projects WHERE id = ?", (pid,))


# ---------------------------------------------------------------- video
def upsert_video(pid: str, meta: dict, filename: str) -> None:
    with connect() as c:
        c.execute(
            """
            INSERT INTO videos (project_id, filename, path, duration, width, height,
                                fps, has_audio, size_bytes, meta_json)
            VALUES (:pid, :fn, :path, :dur, :w, :h, :fps, :au, :sz, :mj)
            ON CONFLICT(project_id) DO UPDATE SET
                filename=:fn, path=:path, duration=:dur, width=:w, height=:h,
                fps=:fps, has_audio=:au, size_bytes=:sz, meta_json=:mj
            """,
            {
                "pid": pid, "fn": filename, "path": meta["path"],
                "dur": meta["duration"], "w": meta["width"], "h": meta["height"],
                "fps": meta["fps"], "au": int(meta["has_audio"]),
                "sz": meta.get("size_bytes", 0), "mj": json.dumps(meta),
            },
        )


# ---------------------------------------------------------------- transcript
def upsert_transcript(pid: str, language: str, backend: str, model: str,
                      has_word_ts: bool, n_segments: int, path: str) -> None:
    with connect() as c:
        c.execute(
            """
            INSERT INTO transcripts (project_id, language, backend, model, has_word_ts,
                                     n_segments, path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                language=excluded.language, backend=excluded.backend,
                model=excluded.model, has_word_ts=excluded.has_word_ts,
                n_segments=excluded.n_segments, path=excluded.path
            """,
            (pid, language, backend, model, int(has_word_ts), n_segments, path),
        )


# ---------------------------------------------------------------- clips
def _clip_row_to_dict(r: dict) -> dict:
    r["score"] = json.loads(r.get("score_json") or "{}")
    r["emphasis_words"] = json.loads(r.get("emphasis_json") or "[]")
    r["self_contained"] = bool(r.get("self_contained"))
    r["llm_used"] = bool(r.get("llm_used"))
    return r


def replace_clips(pid: str, clips: list[dict]) -> None:
    with connect() as c:
        c.execute("DELETE FROM clips WHERE project_id = ?", (pid,))
        for cl in clips:
            c.execute(
                """
                INSERT INTO clips (id, project_id, idx, start, end, duration, category,
                    hook, alt_hook, opening_text, reason, self_contained, score_overall,
                    score_json, text, emphasis_json, llm_used, render_status, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    f"{pid}-{cl['index']:02d}", pid, cl["index"], cl["start"], cl["end"],
                    cl["duration"], cl["category"], cl["hook"], cl["alt_hook"],
                    cl["opening_text"], cl["reason"], int(cl["self_contained"]),
                    cl["score"]["overall"], json.dumps(cl["score"]), cl["text"],
                    json.dumps(cl.get("emphasis_words", [])), int(cl.get("llm_used", False)),
                    "pending", now(),
                ),
            )


def update_clip_render(clip_id: str, *, status: str, render_path: str | None = None,
                       srt_path: str | None = None, ass_path: str | None = None,
                       thumb_path: str | None = None) -> None:
    with connect() as c:
        c.execute(
            """UPDATE clips SET render_status=?, render_path=COALESCE(?, render_path),
                srt_path=COALESCE(?, srt_path), ass_path=COALESCE(?, ass_path),
                thumb_path=COALESCE(?, thumb_path), updated_at=? WHERE id=?""",
            (status, render_path, srt_path, ass_path, thumb_path, now(), clip_id),
        )


def get_clip(clip_id: str) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        return _clip_row_to_dict(dict(r)) if r else None


# ---------------------------------------------------------------- jobs
def enqueue_job(job_id: str, kind: str, project_id: str | None, params: dict,
                priority: int = 0) -> str:
    with connect() as c:
        c.execute(
            """INSERT INTO jobs (id, project_id, kind, state, priority, params_json,
               created_at) VALUES (?, ?, ?, 'queued', ?, ?, ?)""",
            (job_id, project_id, kind, priority, json.dumps(params), now()),
        )
    return job_id


def claim_next_job() -> dict | None:
    with connect() as c:
        row = c.execute(
            "SELECT * FROM jobs WHERE state = 'queued' ORDER BY priority DESC, created_at LIMIT 1"
        ).fetchone()
        if not row:
            return None
        c.execute(
            "UPDATE jobs SET state='processing', started_at=?, attempts=attempts+1 WHERE id=?",
            (now(), row["id"]),
        )
        d = dict(row)
        d["params"] = json.loads(d.get("params_json") or "{}")
        return d


def update_job(job_id: str, *, stage: str | None = None, progress: float | None = None,
               message: str | None = None) -> None:
    with connect() as c:
        c.execute(
            """UPDATE jobs SET stage=COALESCE(?, stage), progress=COALESCE(?, progress),
               message=COALESCE(?, message) WHERE id=?""",
            (stage, progress, message, job_id),
        )


def finish_job(job_id: str, state: str, error: str | None = None) -> None:
    with connect() as c:
        c.execute(
            "UPDATE jobs SET state=?, error=?, finished_at=?, progress=? WHERE id=?",
            (state, error, now(), 1.0 if state == "completed" else None, job_id),
        )


def get_job(job_id: str) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["params"] = json.loads(d.get("params_json") or "{}")
        return d


def list_jobs(project_id: str | None = None, limit: int = 50) -> list[dict]:
    with connect() as c:
        if project_id:
            rows = c.execute(
                "SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def requeue_stale_jobs(older_than: float = 3600.0) -> int:
    """On worker startup, reset jobs stuck in 'processing' (crash recovery)."""
    with connect() as c:
        cur = c.execute(
            "UPDATE jobs SET state='queued' WHERE state='processing' AND "
            "(started_at IS NULL OR started_at < ?)",
            (now() - older_than,),
        )
        return cur.rowcount


# ---------------------------------------------------------------- settings
def get_setting(key: str, default: Any = None) -> Any:
    with connect() as c:
        r = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not r:
            return default
        try:
            return json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            return r["value"]


def set_setting(key: str, value: Any) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


def all_settings() -> dict[str, Any]:
    with connect() as c:
        rows = c.execute("SELECT key, value FROM settings").fetchall()
        out: dict[str, Any] = {}
        for r in rows:
            try:
                out[r["key"]] = json.loads(r["value"])
            except (json.JSONDecodeError, TypeError):
                out[r["key"]] = r["value"]
        return out

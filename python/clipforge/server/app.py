"""ClipForge local API (FastAPI).

Run with:  python -m clipforge.server.app   (or `npm run api`)
Pairs with the background worker (`python -m clipforge.server.worker`).

Everything is local: the API only binds to 127.0.0.1 by default and only serves
files from under the configured data directory.
"""

from __future__ import annotations

import mimetypes
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ..config import get_settings
from ..logging_setup import get_logger, setup_logging
from ..util.errors import ClipForgeError
from ..util.fsutil import (
    SUPPORTED_VIDEO_EXT, ensure_project_tree, new_project_id, safe_join,
    sanitize_filename, write_json,
)
from .. import __version__, db
from ..doctor import summary as doctor_summary
from ..ai.ollama_client import OllamaClient
from ..video.probe import probe_video

log = get_logger("clipforge.api")
setup_logging()

_settings = get_settings()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    db.init_db()
    n = db.requeue_stale_jobs()
    log.info("API up (v%s). data=%s  requeued=%d", __version__, _settings.data_dir, n)
    yield


app = FastAPI(title="ClipForge API", version=__version__, lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_list() or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ClipForgeError)
def _cf_error(_req, exc: ClipForgeError):
    return JSONResponse(status_code=400, content={"error": exc.as_dict()})


# --------------------------------------------------------------------------
# models
# --------------------------------------------------------------------------
class CreateProject(BaseModel):
    name: str = Field(default="Untitled project", max_length=200)
    style: str = Field(default="general")


class AnalyzeRequest(BaseModel):
    n_clips: int = Field(default=5, ge=1, le=20)
    clip_length: str = "auto"
    style: str = "general"
    use_llm: bool = True
    topic_hint: str = ""
    render: bool = True
    reframe_mode: str = "smart_auto"
    caption_style: str = "bold"
    use_captions: bool = True
    enhance_audio: bool = True
    force: bool = False


class RenderClipRequest(BaseModel):
    reframe_mode: str | None = None
    caption_style: str | None = None
    use_captions: bool = True
    enhance_audio: bool = True
    start: float | None = None
    end: float | None = None
    hook: str | None = None
    opening_text: str | None = None
    highlight_words: list[str] | None = None


class SettingsPatch(BaseModel):
    values: dict[str, Any]


# --------------------------------------------------------------------------
# meta / setup
# --------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


@app.get("/api/setup")
def setup():
    return doctor_summary()


@app.get("/api/settings")
def get_settings_route():
    s = get_settings(reload=True)
    s.apply_overrides(db.all_settings())
    d = s.to_dict()
    d["_overrides"] = db.all_settings()
    return d


@app.put("/api/settings")
def put_settings(patch: SettingsPatch):
    allowed = set(get_settings().to_dict().keys())
    saved = {}
    for k, v in patch.values.items():
        if k in allowed:
            db.set_setting(k, v)
            saved[k] = v
    return {"saved": saved}


@app.get("/api/ollama/models")
def ollama_models():
    s = get_settings(reload=True)
    s.apply_overrides(db.all_settings())
    client = OllamaClient(s.ollama_base_url)
    if not client.ping():
        return {"reachable": False, "models": [], "base_url": s.ollama_base_url}
    try:
        return {"reachable": True, "models": client.list_models(),
                "base_url": s.ollama_base_url, "selected": s.model_name}
    except ClipForgeError:
        return {"reachable": True, "models": [], "base_url": s.ollama_base_url}


# --------------------------------------------------------------------------
# projects
# --------------------------------------------------------------------------
@app.post("/api/projects")
def create_project(body: CreateProject):
    pid = new_project_id()
    pdir = _settings.project_dir(pid)
    ensure_project_tree(pdir)
    db.create_project(pid, sanitize_filename(body.name, default="project") or "project",
                      body.style)
    return {"id": pid, "name": body.name, "style": body.style, "status": "created"}


@app.get("/api/projects")
def list_projects():
    rows = db.list_projects()
    for r in rows:
        r["thumbnail_url"] = _first_thumb_url(r["id"])
    return {"projects": rows}


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    proj = db.get_project(pid)
    if not proj:
        raise HTTPException(404, "Project not found")
    proj["media"] = _project_media(pid)
    from ..util.fsutil import read_json
    # attach a short transcript preview
    tpath = _settings.project_dir(pid) / "transcript.json"
    if tpath.exists():
        t = read_json(tpath, {})
        proj["transcript_preview"] = " ".join(
            s.get("text", "") for s in t.get("segments", [])[:6]
        )[:600]
    # surface non-fatal analysis warnings (e.g. damaged/partial audio)
    apath = _settings.project_dir(pid) / "analysis.json"
    if apath.exists():
        proj["warnings"] = read_json(apath, {}).get("warnings", []) or []
    return proj


@app.get("/api/projects/{pid}/transcript")
def get_transcript(pid: str):
    tpath = _settings.project_dir(pid) / "transcript.json"
    if not tpath.exists():
        raise HTTPException(404, "No transcript yet")
    from ..util.fsutil import read_json
    return read_json(tpath, {})


@app.get("/api/projects/{pid}/clips")
def get_clips(pid: str):
    proj = db.get_project(pid)
    if not proj:
        raise HTTPException(404, "Project not found")
    clips = proj["clips"]
    for c in clips:
        _attach_clip_urls(pid, c)
    return {"clips": clips}


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    proj = db.get_project(pid)
    if not proj:
        raise HTTPException(404, "Project not found")
    db.delete_project(pid)
    import shutil
    pdir = _settings.project_dir(pid)
    if pdir.exists():
        shutil.rmtree(pdir, ignore_errors=True)
    return {"deleted": pid}


@app.post("/api/projects/{pid}/upload")
async def upload_video(pid: str, file: UploadFile = File(...)):
    proj = db.get_project(pid)
    if not proj:
        raise HTTPException(404, "Project not found")

    safe_name = sanitize_filename(file.filename or "video.mp4")
    ext = Path(safe_name).suffix.lower()
    if ext not in SUPPORTED_VIDEO_EXT:
        raise ClipForgeError(
            f"Unsupported file type {ext or '(none)'!r}.",
            hint="Supported: " + ", ".join(sorted(SUPPORTED_VIDEO_EXT)),
        )

    pdir = _settings.project_dir(pid)
    ensure_project_tree(pdir)
    dst = pdir / ("original" + ext)

    size = 0
    with dst.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)
    if size < 1024:
        dst.unlink(missing_ok=True)
        raise ClipForgeError("Uploaded file is empty or truncated.")

    try:
        meta = probe_video(dst)
    except ClipForgeError:
        dst.unlink(missing_ok=True)
        raise
    write_json(pdir / "meta.json", meta.to_dict())
    db.upsert_video(pid, meta.to_dict(), safe_name)
    db.set_project_status(pid, "uploaded")

    return {
        "id": pid,
        "filename": safe_name,
        "meta": meta.to_dict(),
        "media": _project_media(pid),
    }


@app.post("/api/projects/{pid}/analyze")
def analyze_project(pid: str, body: AnalyzeRequest):
    proj = db.get_project(pid)
    if not proj:
        raise HTTPException(404, "Project not found")
    if not proj.get("video"):
        raise ClipForgeError("Upload a video before analysing.")

    job_id = uuid.uuid4().hex[:16]
    params = {
        "n_clips": body.n_clips,
        "clip_length": body.clip_length,
        "style": body.style,
        "use_llm": body.use_llm,
        "topic_hint": body.topic_hint,
        "reframe_mode": body.reframe_mode,
        "caption_style": body.caption_style,
        "use_captions": body.use_captions,
        "enhance_audio": body.enhance_audio,
        "force": body.force,
    }
    db.enqueue_job(job_id, "full" if body.render else "analyze", pid, params, priority=5)
    db.set_project_status(pid, "queued")
    return {"job_id": job_id, "kind": "full" if body.render else "analyze"}


@app.post("/api/projects/{pid}/render")
def render_project(pid: str, body: AnalyzeRequest):
    proj = db.get_project(pid)
    if not proj:
        raise HTTPException(404, "Project not found")
    job_id = uuid.uuid4().hex[:16]
    params = {
        "reframe_mode": body.reframe_mode,
        "caption_style": body.caption_style,
        "use_captions": body.use_captions,
        "enhance_audio": body.enhance_audio,
        "force": body.force,
    }
    db.enqueue_job(job_id, "render", pid, params, priority=3)
    return {"job_id": job_id, "kind": "render"}


@app.post("/api/clips/{clip_id}/render")
def render_clip(clip_id: str, body: RenderClipRequest):
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(404, "Clip not found")
    pid = clip["project_id"]

    # allow editor tweaks: persist start/end/hook overrides into analysis.json
    pdir = _settings.project_dir(pid)
    apath = pdir / "analysis.json"
    if apath.exists() and (body.start is not None or body.hook is not None
                           or body.opening_text is not None
                           or body.highlight_words is not None):
        from ..util.fsutil import read_json
        analysis = read_json(apath, {})
        for c in analysis.get("clips", []):
            if c["index"] == clip["idx"]:
                if body.start is not None:
                    c["start"] = max(0.0, float(body.start))
                if body.end is not None:
                    c["end"] = float(body.end)
                    c["duration"] = round(c["end"] - c["start"], 3)
                if body.hook is not None:
                    c["hook"] = body.hook[:120]
                if body.opening_text is not None:
                    c["opening_text"] = body.opening_text[:80]
                if body.highlight_words is not None:
                    c["emphasis_words"] = body.highlight_words[:8]
        write_json(apath, analysis)

    job_id = uuid.uuid4().hex[:16]
    params = {
        "clip_index": clip["idx"],
        "reframe_mode": body.reframe_mode,
        "caption_style": body.caption_style,
        "use_captions": body.use_captions,
        "enhance_audio": body.enhance_audio,
    }
    db.enqueue_job(job_id, "render_clip", pid, params, priority=8)
    db.update_clip_render(clip_id, status="pending")
    return {"job_id": job_id}


# --------------------------------------------------------------------------
# jobs
# --------------------------------------------------------------------------
@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/projects/{pid}/jobs")
def project_jobs(pid: str):
    return {"jobs": db.list_jobs(pid)}


# --------------------------------------------------------------------------
# media / downloads
# --------------------------------------------------------------------------
@app.get("/api/media/{pid}/{kind}/{name}")
def media(pid: str, kind: str, name: str):
    if kind not in {"renders", "thumbnails", "clips", "."}:
        kind = "renders"
    base = _settings.project_dir(pid)
    try:
        if kind == ".":
            target = safe_join(base, name)
        else:
            target = safe_join(base, kind, name)
    except ValueError:
        raise HTTPException(400, "Bad path")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Not found")
    mime, _ = mimetypes.guess_type(str(target))
    return FileResponse(str(target), media_type=mime or "application/octet-stream",
                        filename=target.name)


@app.get("/api/projects/{pid}/original")
def original(pid: str):
    base = _settings.project_dir(pid)
    for cand in base.glob("original.*"):
        mime, _ = mimetypes.guess_type(str(cand))
        return FileResponse(str(cand), media_type=mime or "video/mp4")
    raise HTTPException(404, "No original video")


@app.get("/api/clips/{clip_id}/download")
def download_clip(clip_id: str):
    clip = db.get_clip(clip_id)
    if not clip or not clip.get("render_path"):
        raise HTTPException(404, "Clip not rendered yet")
    p = Path(clip["render_path"])
    if not p.exists():
        raise HTTPException(404, "Render file missing")
    return FileResponse(str(p), media_type="video/mp4", filename=p.name)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _project_media(pid: str) -> dict:
    base = _settings.project_dir(pid)
    has_original = any(base.glob("original.*"))
    return {
        "original_url": f"/api/projects/{pid}/original" if has_original else None,
    }


def _first_thumb_url(pid: str) -> str | None:
    base = _settings.project_dir(pid) / "renders"
    if base.exists():
        jpgs = sorted(base.glob("*.jpg"))
        if jpgs:
            return f"/api/media/{pid}/renders/{jpgs[0].name}"
    thumbs = _settings.project_dir(pid) / "thumbnails"
    if thumbs.exists():
        jpgs = sorted(thumbs.glob("*.jpg"))
        if jpgs:
            return f"/api/media/{pid}/thumbnails/{jpgs[0].name}"
    return None


def _attach_clip_urls(pid: str, c: dict) -> None:
    for field, kind in (("render_path", "renders"), ("thumb_path", "renders"),
                        ("srt_path", "renders"), ("ass_path", "renders")):
        p = c.get(field)
        if p and Path(p).exists():
            c[field.replace("_path", "_url")] = f"/api/media/{pid}/renders/{Path(p).name}"
        else:
            c[field.replace("_path", "_url")] = None
    c["download_url"] = f"/api/clips/{c['id']}/download" if c.get("render_path") else None


def main() -> None:
    import uvicorn
    s = get_settings()
    uvicorn.run(
        "clipforge.server.app:app",
        host=s.api_host, port=s.api_port, reload=False, log_level="info",
    )


if __name__ == "__main__":
    main()

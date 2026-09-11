"""Job execution — maps a job row to a pipeline call and streams progress to the
``jobs`` table so the frontend can poll ``GET /api/jobs/:id``.

Job kinds
---------
* ``analyze``  params: {n_clips, clip_length, style, use_llm, topic_hint, force}
* ``render``   params: {reframe_mode, caption_style, use_captions, enhance_audio,
                        only_indexes, force}
* ``full``     params: analyze + render params merged
* ``render_clip`` params: {clip_index, ...render params}  (single clip re-render)
"""

from __future__ import annotations

import time
from pathlib import Path

from ..config import get_settings, Settings
from ..db import (
    finish_job, get_project, replace_clips, set_project_status, update_clip_render,
    update_job, upsert_transcript, upsert_video,
)
from ..logging_setup import get_logger
from ..util.errors import ClipForgeError
from ..util.fsutil import read_json, sanitize_filename
from .. import pipeline

log = get_logger("clipforge.jobs")


def _settings_with_overrides() -> Settings:
    from ..db import all_settings
    s = get_settings(reload=True)
    try:
        s.apply_overrides(all_settings())
    except Exception:  # DB may be new
        pass
    return s


def _progress_writer(job_id: str, pid: str | None = None):
    last = [0.0]

    def cb(frac: float, stage: str, msg: str) -> None:
        # throttle DB writes a little
        now = time.time()
        if frac >= 1.0 or now - last[0] > 0.4:
            last[0] = now
            # If the project was deleted while this stage was running, stop
            # instead of grinding on into a directory that no longer exists
            # (or worse, one silently recreated under it).
            if pid and not get_project(pid):
                raise ClipForgeError("Project was deleted; aborting job.")
            update_job(job_id, stage=stage, progress=round(float(frac), 4), message=msg)

    return cb


def _find_source(project_dir: Path, meta_path: Path) -> Path:
    meta = read_json(meta_path, {})
    if meta.get("path") and Path(meta["path"]).exists():
        return Path(meta["path"])
    for cand in project_dir.glob("original.*"):
        return cand
    raise ClipForgeError("Original video file is missing for this project.")


def run_job(job: dict) -> None:
    job_id = job["id"]
    kind = job["kind"]
    pid = job["project_id"]
    params = job.get("params", {})
    s = _settings_with_overrides()
    cb = _progress_writer(job_id, pid)

    project = get_project(pid) if pid else None
    if pid and not project:
        finish_job(job_id, "failed", "Project not found.")
        return

    project_dir = s.project_dir(pid)
    project_dir.mkdir(parents=True, exist_ok=True)

    try:
        if kind in ("analyze", "full"):
            set_project_status(pid, "processing")
            src = _find_source(project_dir, project_dir / "meta.json")
            aopts = pipeline.AnalyzeOptions(
                n_clips=int(params.get("n_clips", s.default_clips)),
                clip_length=str(params.get("clip_length", "auto")),
                style=params.get("style", "general"),
                use_llm=bool(params.get("use_llm", True)),
                topic_hint=params.get("topic_hint", ""),
            )
            if kind == "analyze":
                analysis = pipeline.analyze(
                    project_dir, src, aopts, settings=s, on_progress=cb,
                    force=bool(params.get("force", False)),
                )
            else:
                ropts = _render_opts(params, s)
                analysis = pipeline.run(
                    project_dir, src, aopts, ropts, settings=s, on_progress=cb,
                    force=bool(params.get("force", False)),
                )

            upsert_video(pid, analysis["meta"], project["video"]["filename"]
                         if project.get("video") else sanitize_filename(src.name))
            upsert_transcript(
                pid, analysis.get("language", "en"),
                analysis.get("transcript_backend", ""),
                analysis.get("transcript_model", ""),
                analysis.get("has_word_timestamps", False),
                analysis.get("n_candidates", 0),
                str(project_dir / "transcript.json"),
            )
            replace_clips(pid, analysis["clips"])
            for r in analysis.get("renders", []):
                _apply_render_result(pid, r)
            set_project_status(pid, "completed")

        elif kind == "render":
            src = _find_source(project_dir, project_dir / "meta.json")
            ropts = _render_opts(params, s)
            results = pipeline.render(
                project_dir, ropts, settings=s, on_progress=cb,
                force=bool(params.get("force", False)),
            )
            for r in results:
                _apply_render_result(pid, r)
            set_project_status(pid, "completed")

        elif kind == "render_clip":
            src = _find_source(project_dir, project_dir / "meta.json")
            idx = int(params["clip_index"])
            ropts = _render_opts(params, s)
            ropts.only_indexes = [idx]
            results = pipeline.render(
                project_dir, ropts, settings=s, on_progress=cb, force=True,
            )
            for r in results:
                _apply_render_result(pid, r)

        else:
            raise ClipForgeError(f"Unknown job kind: {kind}")

        finish_job(job_id, "completed")
        log.info("job %s (%s) completed", job_id, kind)

    except ClipForgeError as e:
        log.error("job %s failed: %s", job_id, e.message)
        if pid:
            set_project_status(pid, "failed", e.message)
        finish_job(job_id, "failed", e.message)
    except Exception as e:  # pragma: no cover - defensive catch-all
        log.exception("job %s crashed", job_id)
        if pid:
            set_project_status(pid, "failed", "Internal error while processing.")
        finish_job(job_id, "failed", f"{type(e).__name__}: {e}")


def _render_opts(params: dict, s: Settings) -> "pipeline.RenderOptions":
    return pipeline.RenderOptions(
        reframe_mode=params.get("reframe_mode", s.reframe_mode),
        caption_style=params.get("caption_style", s.caption_style),
        use_captions=bool(params.get("use_captions", True)),
        enhance_audio=bool(params.get("enhance_audio", s.enhance_audio)),
        use_ai_hooks=bool(params.get("use_ai_hooks", s.use_ai_hooks)),
        only_indexes=[int(x) for x in params.get("only_indexes", [])],
    )


def _apply_render_result(pid: str, r: dict) -> None:
    clip_id = f"{pid}-{int(r['index']):02d}"
    if r.get("status") == "completed":
        update_clip_render(
            clip_id, status="completed",
            render_path=r.get("mp4"), srt_path=r.get("srt"),
            ass_path=r.get("ass"), thumb_path=r.get("thumbnail"),
        )
    else:
        update_clip_render(clip_id, status="failed")

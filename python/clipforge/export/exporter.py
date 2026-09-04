"""Render one :class:`Clip` to disk: MP4 + optional .srt / .ass sidecars.

This is the reusable unit the pipeline and the worker's "render single clip"
job both call. It caches: if the MP4 already exists and inputs are unchanged it
returns immediately.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..logging_setup import get_logger
from ..models import Clip, VideoMeta
from ..captions import CaptionOptions, build_ass, build_srt
from ..video.frames import sample_face_track
from ..video.reframe import plan_crop
from ..video.render import RenderRequest, make_thumbnail, render_clip
from .naming import clip_filename, clip_slug

log = get_logger("clipforge.export")


@dataclass
class ExportResult:
    clip_index: int
    mp4: Path
    srt: Path | None
    ass: Path | None
    thumbnail: Path | None
    duration: float
    cached: bool


def _fingerprint(clip: Clip, settings: Settings, reframe_mode: str, caption_style: str,
                 use_captions: bool, enhance: bool) -> str:
    h = hashlib.sha1()
    h.update(json.dumps({
        "start": round(clip.start, 2),
        "end": round(clip.end, 2),
        "mode": reframe_mode,
        "style": caption_style,
        "caps": use_captions,
        "enh": enhance,
        "w": settings.output_width,
        "h": settings.output_height,
        "fps": settings.output_fps,
        "crf": settings.video_crf,
        "hook": clip.hook,
        "emph": clip.emphasis_words,
    }, sort_keys=True).encode())
    return h.hexdigest()[:16]


def export_clip(
    clip: Clip,
    *,
    src_video: Path,
    meta: VideoMeta,
    out_dir: Path,
    settings: Settings,
    reframe_mode: str | None = None,
    caption_style: str | None = None,
    use_captions: bool = True,
    enhance_audio: bool | None = None,
    enhanced_audio_path: Path | None = None,
    highlight_words: list[str] | None = None,
    frames_dir: Path | None = None,
    progress=None,
    force: bool = False,
    top: bool = False,
) -> ExportResult:
    reframe_mode = reframe_mode or settings.reframe_mode
    caption_style = caption_style or settings.caption_style
    enhance_audio = settings.enhance_audio if enhance_audio is None else enhance_audio

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = clip.slug or clip_slug(clip.hook or clip.category)
    clip.slug = slug
    fname = clip_filename(clip.index, clip.category, clip.hook, top=top)
    mp4_path = out_dir / fname
    fp_path = out_dir / (mp4_path.stem + ".fingerprint")
    fp = _fingerprint(clip, settings, reframe_mode, caption_style, use_captions, bool(enhance_audio))

    if not force and mp4_path.exists() and fp_path.exists() and fp_path.read_text().strip() == fp:
        srt = out_dir / (mp4_path.stem + ".srt")
        ass = out_dir / (mp4_path.stem + ".ass")
        thumb = out_dir / (mp4_path.stem + ".jpg")
        if progress:
            progress(1.0, "Using cached render")
        return ExportResult(
            clip.index, mp4_path,
            srt if srt.exists() else None,
            ass if ass.exists() else None,
            thumb if thumb.exists() else None,
            clip.duration, cached=True,
        )

    # --- captions ---
    ass_path = None
    srt_path = None
    if use_captions and clip.segments:
        hl = list(highlight_words or clip.emphasis_words or [])
        copt = CaptionOptions(
            style=caption_style,
            play_w=settings.output_width,
            play_h=settings.output_height,
            highlight_words=hl,
        )
        has_word_ts = any(s.words for s in clip.segments)
        ass_text = build_ass(
            clip.segments, copt,
            clip_start=clip.start,
            has_word_timestamps=has_word_ts,
            opening_text=clip.opening_text or "",
        )
        ass_path = out_dir / (mp4_path.stem + ".ass")
        ass_path.write_text(ass_text, encoding="utf-8")

        srt_text = build_srt(clip.segments, clip_start=clip.start)
        srt_path = out_dir / (mp4_path.stem + ".srt")
        srt_path.write_text(srt_text, encoding="utf-8")

    # --- reframe plan ---
    if progress:
        progress(0.05, "Analysing framing")
    observations = []
    if reframe_mode in ("smart_auto", "face", "speaker"):
        observations = sample_face_track(
            src_video, clip.start, clip.end,
            fps=4.0,
            frame_dir=frames_dir or (out_dir.parent / "frames"),
        )
    plan = plan_crop(
        meta, clip.start, clip.end, observations,
        mode=reframe_mode,
        out_w=settings.output_width,
        out_h=settings.output_height,
    )

    # --- render ---
    req = RenderRequest(
        src_video=Path(src_video),
        out_path=mp4_path,
        start=clip.start,
        end=clip.end,
        plan=plan,
        ass_path=ass_path,
        enhanced_audio=enhanced_audio_path if enhance_audio else None,
        settings=settings,
        meta=meta,
    )
    render_clip(req, progress=progress)
    fp_path.write_text(fp, encoding="utf-8")

    thumb = out_dir / (mp4_path.stem + ".jpg")
    make_thumbnail(mp4_path, clip.duration * 0.35, thumb, width=540)

    return ExportResult(
        clip.index, mp4_path, srt_path, ass_path,
        thumb if thumb.exists() else None,
        clip.duration, cached=False,
    )

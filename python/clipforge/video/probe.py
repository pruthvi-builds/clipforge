"""Inspect a video with ffprobe and return a :class:`VideoMeta`."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..logging_setup import get_logger
from ..models import VideoMeta
from ..util.errors import CorruptVideoError, MissingDependencyError, UnsupportedFileError
from ..util.fsutil import SUPPORTED_VIDEO_EXT
from ..util.shell import require, run

log = get_logger("clipforge.probe")

FFPROBE_HINT = "Install FFmpeg (which includes ffprobe): `brew install ffmpeg`"


def _parse_fraction(value: str | None) -> float:
    if not value:
        return 0.0
    if "/" in value:
        num, _, den = value.partition("/")
        try:
            d = float(den)
            return float(num) / d if d else 0.0
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def probe_video(path: str | Path) -> VideoMeta:
    path = Path(path)
    if not path.exists():
        raise UnsupportedFileError(f"File does not exist: {path.name}")
    if path.suffix.lower() not in SUPPORTED_VIDEO_EXT:
        raise UnsupportedFileError(
            f"Unsupported file type {path.suffix!r}.",
            hint=f"Supported: {', '.join(sorted(SUPPORTED_VIDEO_EXT))}",
        )

    ffprobe = require("ffprobe", install_hint=FFPROBE_HINT)
    res = run(
        [
            ffprobe, "-v", "error", "-hide_banner",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(path),
        ],
        check=False,
        timeout=120,
    )
    if res.returncode != 0 or not res.stdout.strip():
        raise CorruptVideoError(
            "This file could not be read as a video. It may be corrupt or incomplete.",
            hint=res.stderr.strip().splitlines()[-1] if res.stderr.strip() else None,
        )

    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError as e:  # pragma: no cover - defensive
        raise CorruptVideoError("ffprobe returned unreadable output.") from e

    fmt = data.get("format", {})
    streams = data.get("streams", [])
    vstreams = [s for s in streams if s.get("codec_type") == "video"]
    astreams = [s for s in streams if s.get("codec_type") == "audio"]

    if not vstreams:
        raise UnsupportedFileError("No video stream found in this file.")

    v = vstreams[0]
    duration = _parse_fraction(fmt.get("duration")) or _parse_fraction(v.get("duration"))
    fps = _parse_fraction(v.get("avg_frame_rate")) or _parse_fraction(v.get("r_frame_rate"))
    width = int(v.get("width") or 0)
    height = int(v.get("height") or 0)

    # apply rotation metadata so width/height reflect the displayed frame
    rotation = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            try:
                rotation = int(sd["rotation"])
            except (TypeError, ValueError):
                rotation = 0
    tags_rot = (v.get("tags") or {}).get("rotate")
    if tags_rot:
        try:
            rotation = int(tags_rot)
        except ValueError:
            pass
    if rotation in (90, -90, 270, -270):
        width, height = height, width

    if duration <= 0 or width <= 0 or height <= 0:
        raise CorruptVideoError("Video metadata is missing duration or dimensions.")

    a = astreams[0] if astreams else None
    meta = VideoMeta(
        path=str(path),
        duration=round(duration, 3),
        width=width,
        height=height,
        fps=round(fps, 3) if fps else 30.0,
        has_audio=a is not None,
        video_codec=v.get("codec_name", ""),
        audio_codec=(a or {}).get("codec_name", "") if a else "",
        audio_channels=int((a or {}).get("channels") or 0) if a else 0,
        audio_sample_rate=int((a or {}).get("sample_rate") or 0) if a else 0,
        size_bytes=int(fmt.get("size") or (os.path.getsize(path) if path.exists() else 0)),
        container=(fmt.get("format_name") or "").split(",")[0],
    )
    log.info(
        "probed %s: %.1fs %dx%d @%.2ffps audio=%s",
        path.name, meta.duration, meta.width, meta.height, meta.fps, meta.has_audio,
    )
    return meta

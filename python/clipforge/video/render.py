"""Final clip render: trim + smart 9:16 crop + burned captions + clean audio.

One FFmpeg invocation per clip. Progress is parsed from ``-progress pipe:1``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..logging_setup import get_logger
from ..models import VideoMeta
from ..util.errors import ExportError
from ..util.shell import require, run_streaming
from .reframe import CropPlan

log = get_logger("clipforge.render")

FFMPEG_HINT = "Install FFmpeg: `brew install ffmpeg`"


@dataclass
class RenderRequest:
    src_video: Path
    out_path: Path
    start: float
    end: float
    plan: CropPlan
    ass_path: Path | None
    enhanced_audio: Path | None          # optional pre-rendered enhanced wav (full video timeline)
    settings: Settings
    meta: VideoMeta


def _write_sendcmd(plan: CropPlan, path: Path) -> None:
    lines = []
    max_x = None
    for t, x in plan.keys:
        lines.append(f"{t:.3f} crop x {x};")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _escape_filter_path(p: Path) -> str:
    # libavfilter path escaping for the ass= / sendcmd f= option
    s = str(p)
    s = s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return s


def build_filtergraph(req: RenderRequest, tmp_dir: Path) -> tuple[str, list[str]]:
    s = req.settings
    ow, oh = s.output_width, s.output_height
    plan = req.plan
    extra_inputs: list[str] = []

    vchain = [f"trim=start={req.start:.3f}:end={req.end:.3f}", "setpts=PTS-STARTPTS"]

    if plan.fit:
        # keep the whole frame; scale to fit inside the canvas and pad the rest
        # with black instead of cropping the sides off.
        vchain.append(
            f"scale={ow}:{oh}:force_original_aspect_ratio=decrease:flags=lanczos"
        )
        vchain.append(f"pad={ow}:{oh}:(ow-iw)/2:(oh-ih)/2:color=black")
    else:
        if plan.static:
            x = plan.keys[0][1] if plan.keys else 0
            vchain.append(
                f"crop=w={plan.crop_w}:h={plan.crop_h}:x={x}:y={plan.y_top}"
            )
        else:
            cmd_path = tmp_dir / "crop.cmds"
            _write_sendcmd(plan, cmd_path)
            vchain.append(f"sendcmd=f='{_escape_filter_path(cmd_path)}'")
            vchain.append(
                f"crop=w={plan.crop_w}:h={plan.crop_h}:x={plan.keys[0][1] if plan.keys else 0}:y={plan.y_top}"
            )

        vchain.append(
            f"scale={ow}:{oh}:force_original_aspect_ratio=increase:flags=lanczos"
        )
        vchain.append(f"crop={ow}:{oh}")
    vchain.append(f"fps={s.output_fps}")
    vchain.append("format=yuv420p")
    if req.ass_path and req.ass_path.exists():
        vchain.append(f"ass='{_escape_filter_path(req.ass_path)}'")

    vfilter = "[0:v]" + ",".join(vchain) + "[v]"

    # audio
    if req.enhanced_audio and req.enhanced_audio.exists():
        extra_inputs = ["-i", str(req.enhanced_audio)]
        afilter = (
            f"[1:a]atrim=start={req.start:.3f}:end={req.end:.3f},"
            f"asetpts=PTS-STARTPTS[a]"
        )
        amap = "[a]"
    elif req.meta.has_audio:
        afilter = (
            f"[0:a]atrim=start={req.start:.3f}:end={req.end:.3f},"
            f"asetpts=PTS-STARTPTS[a]"
        )
        amap = "[a]"
    else:
        afilter = ""
        amap = ""

    graph = vfilter + ((";" + afilter) if afilter else "")
    return graph, (extra_inputs + (["-map", "[v]"] + (["-map", amap] if amap else [])))


_OUT_TIME_RE = re.compile(r"out_time_ms=(\d+)")


def render_clip(req: RenderRequest, *, progress=None) -> Path:
    ffmpeg = require("ffmpeg", install_hint=FFMPEG_HINT)
    req.out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = req.out_path.parent / (".tmp_" + req.out_path.stem)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    graph, maps = build_filtergraph(req, tmp_dir)
    duration = max(0.1, req.end - req.start)
    s = req.settings

    args = [
        ffmpeg, "-hide_banner", "-y",
        # tolerate slightly damaged consumer recordings instead of aborting
        "-err_detect", "ignore_err", "-fflags", "+discardcorrupt+igndts",
        "-i", str(req.src_video),
    ]
    # extra inputs (enhanced audio) are already embedded in `maps` prefix
    # split: maps may start with ["-i", path]
    idx = 0
    while idx < len(maps) and maps[idx] == "-i":
        args += [maps[idx], maps[idx + 1]]
        idx += 2
    map_args = maps[idx:]

    args += [
        "-filter_complex", graph,
        *map_args,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", str(s.video_crf),
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-movflags", "+faststart",
        "-r", str(s.output_fps),
    ]
    if "[a]" in graph or "0:a" in "".join(map_args):
        args += ["-c:a", "aac", "-b:a", s.audio_bitrate, "-ar", "48000", "-ac", "2"]
    else:
        args += ["-an"]
    args += [
        "-max_error_rate", "1.0",
        "-progress", "pipe:1", "-nostats",
        str(req.out_path),
    ]

    errbuf: list[str] = []

    def on_line(line: str) -> None:
        errbuf.append(line)
        if len(errbuf) > 200:
            del errbuf[:100]
        m = _OUT_TIME_RE.search(line)
        if m and progress:
            done = int(m.group(1)) / 1_000_000.0
            progress(max(0.0, min(0.99, done / duration)), "Rendering clip")

    code = run_streaming(args, on_line=on_line, stderr=True)
    # cleanup tmp
    try:
        for f in tmp_dir.iterdir():
            f.unlink()
        tmp_dir.rmdir()
    except OSError:
        pass

    if code != 0 or not req.out_path.exists() or req.out_path.stat().st_size < 2048:
        tail = "\n".join(errbuf[-15:])
        raise ExportError(
            "Rendering this clip failed.",
            hint=tail or "Check FFmpeg is installed and the source file is readable.",
        )
    if progress:
        progress(1.0, "Clip rendered")
    log.info("rendered %s (%.1f KB)", req.out_path.name, req.out_path.stat().st_size / 1024)
    return req.out_path


def make_thumbnail(src_video: Path, t: float, out_path: Path, *, width: int = 640) -> Path | None:
    ffmpeg = require("ffmpeg", install_hint=FFMPEG_HINT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    from ..util.shell import run
    res = run(
        [
            ffmpeg, "-hide_banner", "-y",
            "-ss", f"{max(0.0, t):.3f}",
            "-i", str(src_video),
            "-frames:v", "1",
            "-vf", f"scale={width}:-2",
            str(out_path),
        ],
        check=False,
        timeout=60,
    )
    return out_path if (res.returncode == 0 and out_path.exists()) else None

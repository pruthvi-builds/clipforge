"""End-to-end render test.

Creates a real (synthetic) landscape video with ffmpeg, then runs the actual
export pipeline: reframe plan -> ASS captions -> FFmpeg render, and verifies the
output is a real 1080x1920 H.264 MP4 of the right duration.

Marked ``e2e``; skipped automatically if ffmpeg is missing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from clipforge.config import Settings
from clipforge.models import Clip, ClipScore, Segment, Word
from clipforge.video.probe import probe_video
from clipforge.export.exporter import export_clip

pytestmark = pytest.mark.e2e


def _ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def _seg(start, end, text):
    toks = text.split()
    step = (end - start) / max(1, len(toks))
    words = [Word(start=round(start + i * step, 3), end=round(start + (i + 1) * step, 3),
                  text=t) for i, t in enumerate(toks)]
    return Segment(start=start, end=end, text=text, words=words)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_render_produces_vertical_mp4(synth_video, tmp_path):
    meta = probe_video(synth_video)
    assert meta.width == 1280 and meta.height == 720

    s = Settings()
    s.output_width, s.output_height, s.output_fps = 1080, 1920, 30
    s.video_crf = 28  # faster test encode

    clip = Clip(
        index=1, start=1.0, end=7.0,
        text="the biggest mistake was moving too fast and breaking the thing",
        score=ClipScore(overall=80),
        hook="The biggest mistake", alt_hook="", opening_text="Watch this",
        category="story", reason="test", self_contained=True,
        segments=[
            _seg(1.0, 4.0, "the biggest mistake was moving too fast"),
            _seg(4.0, 7.0, "and then everything started breaking down"),
        ],
        emphasis_words=["mistake", "breaking"],
    )

    out_dir = tmp_path / "renders"
    res = export_clip(
        clip, src_video=synth_video, meta=meta, out_dir=out_dir, settings=s,
        reframe_mode="center",           # deterministic; no face in testsrc
        caption_style="bold", use_captions=True, enhance_audio=False,
        top=True,
    )

    assert res.mp4.exists() and res.mp4.stat().st_size > 10_000
    assert res.srt and res.srt.exists()
    assert res.ass and res.ass.exists()

    info = _ffprobe(res.mp4)
    v = next(st for st in info["streams"] if st["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920)
    assert v["codec_name"] == "h264"
    dur = float(info["format"]["duration"])
    assert 5.3 <= dur <= 6.7          # ~6s clip, allow encoder slack

    # filename is human readable, not a uuid
    assert res.mp4.name == "01_highest-potential.mp4"

    # second run hits the cache
    res2 = export_clip(
        clip, src_video=synth_video, meta=meta, out_dir=out_dir, settings=s,
        reframe_mode="center", caption_style="bold", use_captions=True,
        enhance_audio=False, top=True,
    )
    assert res2.cached is True


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_smart_auto_falls_back_to_center_without_faces(synth_video, tmp_path):
    meta = probe_video(synth_video)
    s = Settings()
    s.video_crf = 30
    clip = Clip(
        index=2, start=0.5, end=4.5, text="hello world this is a test clip",
        score=ClipScore(overall=60), hook="Test", alt_hook="", opening_text="",
        category="insight", reason="", self_contained=True,
        segments=[_seg(0.5, 4.5, "hello world this is a test clip")],
    )
    res = export_clip(
        clip, src_video=synth_video, meta=meta, out_dir=tmp_path / "r", settings=s,
        reframe_mode="smart_auto", caption_style="clean", use_captions=True,
        enhance_audio=False,
    )
    info = _ffprobe(res.mp4)
    v = next(st for st in info["streams"] if st["codec_type"] == "video")
    assert (v["width"], v["height"]) == (s.output_width, s.output_height)

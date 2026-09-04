"""Shared fixtures."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clipforge.models import Segment, Transcript, Word  # noqa: E402


def _mk_words(text: str, start: float, wps: float = 2.5) -> list[Word]:
    toks = text.split()
    out = []
    t = start
    for tok in toks:
        dur = max(0.18, len(tok) / 12.0) / wps * 2.5
        out.append(Word(start=round(t, 3), end=round(t + dur, 3), text=tok))
        t += dur + 0.03
    return out


@pytest.fixture
def sample_transcript() -> Transcript:
    """A small synthetic transcript with word timings and a few obvious hooks."""
    lines = [
        (0.0, "Welcome back to the show everyone thanks for tuning in today."),
        (6.0, "So um I guess we can start whenever you are ready."),
        (11.0, "The biggest mistake I made early on was hiring too fast."),
        (16.5, "I spent three years building the wrong product for the wrong customer."),
        (23.0, "Nobody tells you that revenue hides a hundred problems."),
        (29.0, "Here's what happened: we raised ten million dollars and then panicked."),
        (36.0, "We doubled the team in ninety days and everything slowed down."),
        (43.0, "The lesson is simple, stay small until the product actually works."),
        (49.5, "You should measure retention before you spend a dollar on ads."),
        (56.0, "Anyway that's the story, it cost us about two years of runway."),
        (63.0, "And then we recovered by cutting back to a team of four."),
        (69.0, "Thanks again for listening, see you next week take care."),
    ]
    segs: list[Segment] = []
    for i, (start, text) in enumerate(lines):
        end = lines[i + 1][0] - 0.2 if i + 1 < len(lines) else start + 5.0
        words = _mk_words(text, start)
        # keep words inside [start, end]
        if words:
            span = words[-1].end - words[0].start
            scale = (end - start - 0.1) / max(0.1, span)
            for w in words:
                w.start = round(start + (w.start - words[0].start) * scale, 3)
                w.end = round(start + (w.end - words[0].start) * scale, 3)
        segs.append(Segment(start=start, end=round(end, 3), text=text, words=words,
                            avg_logprob=-0.3, no_speech_prob=0.02))
    return Transcript(language="en", segments=segs, backend="synthetic",
                      model="test", has_word_timestamps=True)


@pytest.fixture
def tmp_project() -> Path:
    d = Path(tempfile.mkdtemp(prefix="clipforge-test-"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def synth_video(tmp_path: Path) -> Path:
    """A 12s 1280x720 test video with tone audio, made with ffmpeg lavfi."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    out = tmp_path / "synth.mp4"
    import subprocess
    r = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-y",
            "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=12",
            "-f", "lavfi", "-i", "sine=frequency=220:duration=12",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            str(out),
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not out.exists():
        pytest.skip(f"could not create synth video: {r.stderr[-300:]}")
    return out

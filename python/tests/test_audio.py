"""Audio extraction: real (synthetic) file, partial-decode handling, error path."""

from __future__ import annotations

import shutil
import wave

import pytest

from clipforge.video.audio import AudioResult, extract_audio, wav_seconds
from clipforge.util.errors import NoSpeechError


def _write_silence_wav(path, seconds=2.0, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))


def test_wav_seconds_reads_duration(tmp_path):
    p = tmp_path / "s.wav"
    _write_silence_wav(p, 3.0)
    assert 2.9 < wav_seconds(p) < 3.1
    assert wav_seconds(tmp_path / "missing.wav") == 0.0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_extract_from_clean_video(synth_video, tmp_path):
    out = tmp_path / "a.wav"
    res = extract_audio(synth_video, out, sample_rate=16000, source_seconds=12.0)
    assert isinstance(res, AudioResult)
    assert out.exists()
    assert 11.0 <= res.seconds <= 13.0
    assert res.truncated is False


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_extract_raises_when_no_audio(tmp_path):
    # a video with no audio stream at all
    import subprocess

    v = tmp_path / "silent.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-f", "lavfi",
         "-i", "testsrc=size=320x240:rate=15:duration=3",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v)],
        capture_output=True, check=True,
    )
    with pytest.raises(NoSpeechError):
        extract_audio(v, tmp_path / "a.wav", source_seconds=3.0)

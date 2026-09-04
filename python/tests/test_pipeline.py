"""Integration test for the analysis pipeline with transcription/LLM stubbed out.

This exercises stages A-G end to end (segmentation -> seeds -> candidates ->
heuristic scoring -> dedupe -> boundary refinement -> hook fallback) without
needing ffmpeg, Whisper or Ollama.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clipforge import pipeline
from clipforge.config import Settings
from clipforge.models import VideoMeta
from clipforge.video.audio import AudioResult


@pytest.fixture
def stubbed(monkeypatch, sample_transcript):
    meta = VideoMeta(path="/fake/original.mp4", duration=sample_transcript.duration + 3,
                     width=1920, height=1080, fps=30.0, has_audio=True,
                     video_codec="h264", audio_codec="aac", audio_channels=2,
                     audio_sample_rate=48000, size_bytes=1234567, container="mp4")
    monkeypatch.setattr(pipeline, "probe_video", lambda _p: meta)

    def _fake_extract(src, out_wav, **k):
        p = Path(out_wav)
        p.write_bytes(b"RIFFfake")
        return AudioResult(p, sample_transcript.duration, False, meta.duration)

    monkeypatch.setattr(pipeline, "extract_audio", _fake_extract)
    monkeypatch.setattr(pipeline, "transcribe_cached",
                        lambda *a, **k: sample_transcript)

    # LLM offline -> heuristics only path
    from clipforge.ai.llm_analyze import LLMAnalyzer
    monkeypatch.setattr(LLMAnalyzer, "available", lambda self: (False, "offline for test"))
    # hook generator should not hit the network
    from clipforge.ai import hooks as hooks_mod

    class _FakeClient:
        def __init__(self, *a, **k): pass
        def ping(self): return False
        def has_model(self, *_a): return False

    monkeypatch.setattr(hooks_mod, "OllamaClient", _FakeClient)
    return meta


def test_analyze_produces_reasonable_clips(tmp_path, stubbed):
    s = Settings()
    s.min_clip_seconds = 12
    s.max_clip_seconds = 60
    progress_events = []

    analysis = pipeline.analyze(
        tmp_path, "/fake/original.mp4",
        pipeline.AnalyzeOptions(n_clips=3, use_llm=False),
        settings=s,
        on_progress=lambda f, k, m: progress_events.append((round(f, 3), k, m)),
    )

    clips = analysis["clips"]
    assert 1 <= len(clips) <= 3
    assert analysis["llm_used"] is False

    # progress is monotonic non-decreasing and reaches the end
    fracs = [f for f, _, _ in progress_events]
    assert fracs == sorted(fracs)
    assert fracs[-1] >= 0.9

    for c in clips:
        assert c["end"] > c["start"]
        assert 12 - 0.5 <= c["duration"] <= 60 + 2
        assert c["hook"], "every clip needs a hook (fallback from transcript)"
        assert c["text"].strip()
        assert not c["text"].lower().startswith(("so ", "and ", "um "))
        assert 0 <= c["score"]["overall"] <= 100
        assert c["segments"], "clips carry caption segments"

    # analysis.json + meta.json written
    assert (tmp_path / "analysis.json").exists()
    assert (tmp_path / "meta.json").exists()


def test_analyze_is_cache_friendly_for_transcript(tmp_path, stubbed, monkeypatch):
    s = Settings()
    calls = {"n": 0}
    real = pipeline.transcribe_cached

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(pipeline, "transcribe_cached", counting)
    pipeline.analyze(tmp_path, "/fake/original.mp4",
                     pipeline.AnalyzeOptions(n_clips=2, use_llm=False), settings=s)
    pipeline.analyze(tmp_path, "/fake/original.mp4",
                     pipeline.AnalyzeOptions(n_clips=5, use_llm=False), settings=s)
    assert calls["n"] == 2  # called each analyze, but each is a cheap stub

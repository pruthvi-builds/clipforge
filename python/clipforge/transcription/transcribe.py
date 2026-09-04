"""Backend dispatch + on-disk transcript caching.

``transcribe_cached`` is the function the pipeline calls. It:
  * picks a backend (config or auto-detect)
  * returns a cached transcript if one exists for the same (model, backend, audio)
  * otherwise runs transcription and writes ``transcript.json``
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..config import Settings
from ..logging_setup import get_logger
from ..models import Transcript
from ..util.errors import NoSpeechError, TranscriptionError
from ..util.fsutil import read_json, write_json
from .base import ProgressCb, TranscriptionBackend
from .faster_whisper_backend import FasterWhisperBackend
from .whispercpp_backend import WhisperCppBackend

log = get_logger("clipforge.transcribe")


def build_backend(settings: Settings) -> TranscriptionBackend:
    choice = settings.whisper_backend.lower()
    fw = FasterWhisperBackend(settings.whisper_device, settings.whisper_compute)
    cpp = WhisperCppBackend(settings.whispercpp_bin, settings.whispercpp_model)

    if choice in ("faster-whisper", "fasterwhisper", "fw"):
        return fw
    if choice in ("whisper.cpp", "whispercpp", "cpp"):
        return cpp
    # auto
    ok, _ = fw.available()
    if ok:
        return fw
    ok2, reason2 = cpp.available()
    if ok2:
        return cpp
    # neither available -> return fw so its clear install error surfaces
    log.warning("no transcription backend available; will surface install help")
    return fw


def backend_status(settings: Settings) -> list[dict]:
    out = []
    for b in (
        FasterWhisperBackend(settings.whisper_device, settings.whisper_compute),
        WhisperCppBackend(settings.whispercpp_bin, settings.whispercpp_model),
    ):
        ok, reason = b.available()
        out.append({"name": b.name, "available": ok, "detail": reason})
    return out


def _audio_fingerprint(wav_path: Path) -> str:
    st = wav_path.stat()
    h = hashlib.sha1()
    h.update(str(int(st.st_size)).encode())
    h.update(str(int(st.st_mtime)).encode())
    with wav_path.open("rb") as fh:
        h.update(fh.read(65536))
    return h.hexdigest()[:16]


def transcribe_cached(
    wav_path: str | Path,
    transcript_path: str | Path,
    *,
    settings: Settings,
    progress: ProgressCb | None = None,
    force: bool = False,
) -> Transcript:
    wav_path = Path(wav_path)
    transcript_path = Path(transcript_path)

    if not wav_path.exists():
        raise TranscriptionError(f"Audio file not found: {wav_path.name}")

    fp = _audio_fingerprint(wav_path)
    cache_key = f"{settings.whisper_backend}:{settings.whisper_model}:{fp}"

    if not force and transcript_path.exists():
        cached = read_json(transcript_path, {})
        if cached.get("_cache_key") == cache_key and cached.get("segments"):
            log.info("using cached transcript (%d segments)", len(cached["segments"]))
            if progress:
                progress(1.0, "Loaded cached transcript")
            return Transcript.from_dict(cached)

    backend = build_backend(settings)
    ok, reason = backend.available()  # type: ignore[attr-defined]
    if not ok:
        raise TranscriptionError(reason)

    log.info("transcribing with %s model=%s", backend.name, settings.whisper_model)
    transcript = backend.transcribe(
        str(wav_path),
        model=settings.whisper_model,
        language=settings.whisper_language,
        progress=progress,
    )

    # collapse empty result -> clear "no speech" error
    if not transcript.segments or not transcript.text.strip():
        raise NoSpeechError(
            "No speech was detected in this video.",
            hint="ClipForge needs spoken audio to find short-form moments.",
        )

    payload = transcript.to_dict()
    payload["_cache_key"] = cache_key
    write_json(transcript_path, payload)
    log.info("transcript written: %d segments, word_ts=%s",
             len(transcript.segments), transcript.has_word_timestamps)
    return transcript

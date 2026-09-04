"""faster-whisper backend (CTranslate2). Preferred backend.

Runs fully local. On Apple Silicon it uses the CPU int8 path which is fast and
memory-light for tiny/base/small models.
"""

from __future__ import annotations

import platform
import wave

from ..logging_setup import get_logger
from ..models import Segment, Transcript, Word
from ..util.errors import TranscriptionError
from .base import ProgressCb

log = get_logger("clipforge.whisper.fw")


def _wav_duration(path: str) -> float:
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


class FasterWhisperBackend:
    name = "faster-whisper"

    def __init__(self, device: str = "auto", compute: str = "auto"):
        self._device = device
        self._compute = compute
        self._model = None
        self._model_key: tuple | None = None

    # -- capability check ------------------------------------------------
    def available(self) -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
        except Exception as e:  # pragma: no cover - env dependent
            return (
                False,
                "faster-whisper is not installed. Run `pip install -r requirements.txt`. "
                f"({e.__class__.__name__})",
            )
        return True, "ok"

    # -- internals ----------------------------------------------------
    def _resolve_device_compute(self) -> tuple[str, str]:
        device = self._device
        compute = self._compute
        if device == "auto":
            try:
                import torch  # type: ignore

                if torch.cuda.is_available():
                    device = "cuda"
                else:
                    device = "cpu"
            except Exception:
                device = "cpu"
        if compute == "auto":
            if device == "cuda":
                compute = "float16"
            else:
                # int8 is the sweet spot on Apple Silicon / generic CPU
                compute = "int8"
        return device, compute

    def _load(self, model: str):
        device, compute = self._resolve_device_compute()
        key = (model, device, compute)
        if self._model is not None and self._model_key == key:
            return self._model
        from faster_whisper import WhisperModel

        log.info("loading faster-whisper model=%s device=%s compute=%s (%s)",
                 model, device, compute, platform.machine())
        try:
            self._model = WhisperModel(model, device=device, compute_type=compute)
        except Exception as e:
            # Fall back to the safest possible config before giving up.
            if (device, compute) != ("cpu", "int8"):
                log.warning("model load failed (%s); retrying cpu/int8", e)
                self._model = WhisperModel(model, device="cpu", compute_type="int8")
            else:
                raise TranscriptionError(
                    f"Could not load Whisper model {model!r}: {e}",
                    hint="Try a smaller model (tiny/base) in Settings.",
                ) from e
        self._model_key = key
        return self._model

    # -- main entry ---------------------------------------------------
    def transcribe(
        self,
        wav_path: str,
        *,
        model: str,
        language: str = "auto",
        progress: ProgressCb | None = None,
    ) -> Transcript:
        ok, reason = self.available()
        if not ok:
            raise TranscriptionError(reason)

        whisper_model = self._load(model)
        total = _wav_duration(wav_path)
        lang = None if language in ("auto", "", None) else language

        if progress:
            progress(0.02, "Loading transcription model")

        try:
            seg_iter, info = whisper_model.transcribe(
                wav_path,
                language=lang,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 400},
                beam_size=5,
                condition_on_previous_text=False,
            )
        except Exception as e:
            raise TranscriptionError(f"Transcription failed: {e}") from e

        segments: list[Segment] = []
        for s in seg_iter:
            words = [
                Word(
                    start=round(float(w.start), 3),
                    end=round(float(w.end), 3),
                    text=w.word.strip(),
                    prob=round(float(getattr(w, "probability", 1.0) or 1.0), 4),
                )
                for w in (s.words or [])
                if w.word and w.word.strip()
            ]
            segments.append(
                Segment(
                    start=round(float(s.start), 3),
                    end=round(float(s.end), 3),
                    text=s.text.strip(),
                    words=words,
                    avg_logprob=float(getattr(s, "avg_logprob", 0.0) or 0.0),
                    no_speech_prob=float(getattr(s, "no_speech_prob", 0.0) or 0.0),
                )
            )
            if progress and total:
                progress(min(0.99, s.end / total), "Transcribing")

        if progress:
            progress(1.0, "Transcription complete")

        has_words = any(s.words for s in segments)
        return Transcript(
            language=getattr(info, "language", lang or "en") or "en",
            segments=segments,
            backend=self.name,
            model=model,
            has_word_timestamps=has_words,
        )

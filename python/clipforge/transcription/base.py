"""Transcription backend interface + a shared progress callback type."""

from __future__ import annotations

from typing import Callable, Protocol

from ..models import Transcript

# progress(fraction 0..1, human message)
ProgressCb = Callable[[float, str], None]


class TranscriptionBackend(Protocol):
    name: str

    def available(self) -> tuple[bool, str]:
        """Return (ok, reason). ``reason`` explains what to install if not ok."""
        ...

    def transcribe(
        self,
        wav_path: str,
        *,
        model: str,
        language: str = "auto",
        progress: ProgressCb | None = None,
    ) -> Transcript:
        ...

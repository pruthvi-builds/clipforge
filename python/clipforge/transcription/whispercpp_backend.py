"""whisper.cpp backend (subprocess).

Used when faster-whisper / CTranslate2 wheels are unavailable for your Python
version. Requires a compiled ``whisper-cli`` (or legacy ``main``) binary and a
ggml model file. It emits JSON via ``-oj`` which includes word-level tokens
when ``-ml 1`` style output is requested; we parse the standard ``-oj`` JSON
which contains per-token timestamps.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from ..logging_setup import get_logger
from ..models import Segment, Transcript, Word
from ..util.errors import TranscriptionError
from ..util.shell import run
from .base import ProgressCb

log = get_logger("clipforge.whisper.cpp")


class WhisperCppBackend:
    name = "whisper.cpp"

    def __init__(self, binary: str = "whisper-cli", model_path: str = ""):
        self._binary = binary
        self._model_path = model_path

    def _resolve_binary(self) -> str | None:
        for cand in (self._binary, "whisper-cli", "whisper", "main"):
            p = shutil.which(cand)
            if p:
                return p
        return None

    def available(self) -> tuple[bool, str]:
        b = self._resolve_binary()
        if not b:
            return False, (
                "whisper.cpp binary not found. Build it and put `whisper-cli` on "
                "your PATH, then set CLIPFORGE_WHISPERCPP_MODEL to a ggml model."
            )
        if not self._model_path or not Path(self._model_path).exists():
            return False, (
                f"whisper.cpp model file not found at {self._model_path!r}. "
                "Download e.g. ggml-small.bin from the whisper.cpp models page."
            )
        return True, "ok"

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
        binary = self._resolve_binary()
        assert binary

        if progress:
            progress(0.05, "Running whisper.cpp")

        with tempfile.TemporaryDirectory() as td:
            out_prefix = os.path.join(td, "out")
            args = [
                binary,
                "-m", self._model_path,
                "-f", wav_path,
                "-oj",                       # JSON output
                "-of", out_prefix,
                "-ml", "0",
                "-sow",                      # split on word for word timings
                "-pp",                       # print progress
            ]
            if language not in ("auto", "", None):
                args += ["-l", language]
            res = run(args, check=False, timeout=None)
            if res.returncode != 0:
                raise TranscriptionError(
                    "whisper.cpp failed.",
                    hint="\n".join(res.stderr.strip().splitlines()[-6:]),
                )
            json_path = Path(out_prefix + ".json")
            if not json_path.exists():
                raise TranscriptionError("whisper.cpp produced no JSON output.")
            data = json.loads(json_path.read_text(encoding="utf-8"))

        segments: list[Segment] = []
        for tr in data.get("transcription", []):
            offs = tr.get("offsets", {})
            start = float(offs.get("from", 0)) / 1000.0
            end = float(offs.get("to", 0)) / 1000.0
            text = (tr.get("text") or "").strip()
            words: list[Word] = []
            for tok in tr.get("tokens", []) or []:
                ttext = (tok.get("text") or "").strip()
                if not ttext or ttext.startswith("[_"):
                    continue
                toffs = tok.get("offsets", {})
                words.append(
                    Word(
                        start=round(float(toffs.get("from", 0)) / 1000.0, 3),
                        end=round(float(toffs.get("to", 0)) / 1000.0, 3),
                        text=ttext,
                        prob=float(tok.get("p", 1.0) or 1.0),
                    )
                )
            segments.append(Segment(start=start, end=end, text=text, words=words))
            if progress and data.get("transcription"):
                progress(min(0.99, len(segments) / max(1, len(data["transcription"]))),
                         "Transcribing")

        if progress:
            progress(1.0, "Transcription complete")

        return Transcript(
            language=(data.get("result", {}) or {}).get("language", language) or "en",
            segments=segments,
            backend=self.name,
            model=os.path.basename(self._model_path),
            has_word_timestamps=any(s.words for s in segments),
        )

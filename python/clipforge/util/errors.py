"""User-facing error types.

Every ``ClipForgeError`` carries a short, human-readable message that is safe to
show directly in the UI (no stack traces, no internal paths where avoidable).
"""

from __future__ import annotations


class ClipForgeError(Exception):
    """Base class for all expected, user-presentable failures."""

    #: short machine code, used by the frontend to pick an icon / help link
    code = "error"

    def __init__(self, message: str, *, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "hint": self.hint}


class MissingDependencyError(ClipForgeError):
    code = "missing_dependency"


class UnsupportedFileError(ClipForgeError):
    code = "unsupported_file"


class CorruptVideoError(ClipForgeError):
    code = "corrupt_video"


class NoSpeechError(ClipForgeError):
    code = "no_speech"


class TranscriptionError(ClipForgeError):
    code = "transcription_failed"


class LLMError(ClipForgeError):
    code = "llm_error"


class ExportError(ClipForgeError):
    code = "export_failed"


class ProjectNotFoundError(ClipForgeError):
    code = "project_not_found"

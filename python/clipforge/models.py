"""Plain data models shared across the pipeline.

Kept as dataclasses (not pydantic) so the core engine has no heavy deps; the
FastAPI layer wraps these in response models where needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# --------------------------------------------------------------------------
# Video metadata
# --------------------------------------------------------------------------
@dataclass
class VideoMeta:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    video_codec: str = ""
    audio_codec: str = ""
    audio_channels: int = 0
    audio_sample_rate: int = 0
    size_bytes: int = 0
    container: str = ""

    @property
    def aspect(self) -> float:
        return (self.width / self.height) if self.height else 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# Transcript
# --------------------------------------------------------------------------
@dataclass
class Word:
    start: float
    end: float
    text: str
    prob: float = 1.0
    emphasis: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Segment":
        return Segment(
            start=float(d["start"]),
            end=float(d["end"]),
            text=d.get("text", ""),
            words=[Word(**w) for w in d.get("words", [])],
            avg_logprob=float(d.get("avg_logprob", 0.0)),
            no_speech_prob=float(d.get("no_speech_prob", 0.0)),
        )


@dataclass
class Transcript:
    language: str
    segments: list[Segment]
    backend: str = ""
    model: str = ""
    has_word_timestamps: bool = False

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments).strip()

    @property
    def duration(self) -> float:
        return self.segments[-1].end if self.segments else 0.0

    def words(self) -> list[Word]:
        out: list[Word] = []
        for s in self.segments:
            out.extend(s.words)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "backend": self.backend,
            "model": self.model,
            "has_word_timestamps": self.has_word_timestamps,
            "segments": [s.to_dict() for s in self.segments],
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Transcript":
        return Transcript(
            language=d.get("language", "en"),
            backend=d.get("backend", ""),
            model=d.get("model", ""),
            has_word_timestamps=bool(d.get("has_word_timestamps", False)),
            segments=[Segment.from_dict(s) for s in d.get("segments", [])],
        )


# --------------------------------------------------------------------------
# Clip candidates & scoring
# --------------------------------------------------------------------------
@dataclass
class ClipScore:
    engagement: int = 0
    hook: int = 0
    clarity: int = 0
    self_contained: int = 0
    emotion: int = 0
    novelty: int = 0
    story: int = 0
    actionability: int = 0
    audio_quality: int = 0
    overall: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class Candidate:
    start: float
    end: float
    text: str
    # rule-based signal that seeded this window
    seed_reason: str = ""
    features: dict[str, bool] = field(default_factory=dict)
    # filled in by scoring / LLM
    score: ClipScore = field(default_factory=ClipScore)
    hook: str = ""
    alt_hook: str = ""
    opening_text: str = ""
    category: str = "insight"
    reason: str = ""
    self_contained: bool = True
    llm_used: bool = False
    emphasis_words: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration"] = self.duration
        return d


@dataclass
class Clip:
    """A finalised, boundary-refined clip ready to render."""
    index: int
    start: float
    end: float
    text: str
    score: ClipScore
    hook: str
    alt_hook: str
    opening_text: str
    category: str
    reason: str
    self_contained: bool
    slug: str = ""
    segments: list[Segment] = field(default_factory=list)
    emphasis_words: list[str] = field(default_factory=list)
    llm_used: bool = False

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start": self.start,
            "end": self.end,
            "duration": self.duration,
            "text": self.text,
            "score": self.score.to_dict(),
            "hook": self.hook,
            "alt_hook": self.alt_hook,
            "opening_text": self.opening_text,
            "category": self.category,
            "reason": self.reason,
            "self_contained": self.self_contained,
            "slug": self.slug,
            "emphasis_words": self.emphasis_words,
            "llm_used": self.llm_used,
            "segments": [s.to_dict() for s in self.segments],
        }

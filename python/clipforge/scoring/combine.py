"""STAGE E (part 2) — blend heuristic scores with the local LLM's judgement."""

from __future__ import annotations

from ..models import ClipScore


def _clamp(x: float) -> int:
    return int(max(0, min(100, round(x))))


def blend(heur: ClipScore, llm_overall: int | None, llm_weight: float = 0.5) -> ClipScore:
    """Return a new ClipScore. If ``llm_overall`` is None, heuristics stand alone.

    The LLM only moves the *overall* and *engagement* numbers; the component
    sub-scores remain the transparent heuristic values so the UI never shows a
    number nobody can explain.
    """
    out = ClipScore(**heur.to_dict())
    if llm_overall is None:
        return out
    w = max(0.0, min(1.0, llm_weight))
    out.overall = _clamp((1 - w) * heur.overall + w * llm_overall)
    out.engagement = _clamp((1 - w) * heur.engagement + w * llm_overall)
    return out


def length_penalty(overall: int, duration: float) -> int:
    """Nudge very short / very long clips down a touch (structural, not fake)."""
    if duration < 14:
        return _clamp(overall - 6)
    if duration > 82:
        return _clamp(overall - 5)
    if 20 <= duration <= 62:
        return _clamp(overall + 2)
    return overall

"""STAGE F — remove overlapping / near-duplicate candidates.

Greedy: sort by overall score, keep a candidate only if it does not overlap an
already-kept candidate by more than ``max_overlap`` (measured as intersection
over the shorter clip) and is not textually near-identical.
"""

from __future__ import annotations

from ..models import Candidate
from ..util.text import tokenize


def _time_overlap_ratio(a: Candidate, b: Candidate) -> float:
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    shorter = max(1e-6, min(a.duration, b.duration))
    return inter / shorter


def _text_jaccard(a: str, b: str) -> float:
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def deduplicate(
    candidates: list[Candidate],
    *,
    max_overlap: float = 0.45,
    max_text_sim: float = 0.6,
) -> list[Candidate]:
    ordered = sorted(candidates, key=lambda c: c.score.overall, reverse=True)
    kept: list[Candidate] = []
    for c in ordered:
        clash = False
        for k in kept:
            if _time_overlap_ratio(c, k) > max_overlap or _text_jaccard(c.text, k.text) > max_text_sim:
                clash = True
                break
        if not clash:
            kept.append(c)
    kept.sort(key=lambda c: c.start)
    return kept

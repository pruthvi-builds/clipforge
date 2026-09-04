"""STAGE G — snap clip start/end to natural boundaries.

Given a candidate's rough [start, end], find the nearest sentence boundary using
timed sentences, then pull the exact cut to the nearest inter-word silence so we
never cut mid-word. Finally apply a small configurable pad.
"""

from __future__ import annotations

from ..config import Settings
from ..logging_setup import get_logger
from ..models import Candidate, Segment, Word
from ..util.text import looks_incomplete, starts_awkwardly, strip_leading_filler
from .segment import TimedSentence

log = get_logger("clipforge.boundaries")


def _all_words(sentences: list[TimedSentence]) -> list[Word]:
    out: list[Word] = []
    for s in sentences:
        out.extend(s.words)
    return out


def _nearest_gap_cut(words: list[Word], t: float, *, prefer: str) -> float | None:
    """Return a cut time near ``t`` that falls in a silence between words."""
    if not words:
        return None
    best = None
    for i in range(len(words) - 1):
        gap_start, gap_end = words[i].end, words[i + 1].start
        if gap_end - gap_start < 0.06:
            continue
        mid = (gap_start + gap_end) / 2.0
        dist = abs(mid - t)
        if dist > 2.5:
            continue
        if best is None or dist < best[1]:
            best = (mid, dist)
    if best:
        return round(best[0], 3)
    return None


def refine_boundaries(
    cand: Candidate,
    sentences: list[TimedSentence],
    settings: Settings,
    *,
    video_duration: float,
) -> tuple[float, float, list[Segment], list[str]]:
    """Return (start, end, covered_segments, clean_text_sentences)."""
    pad = settings.boundary_padding

    # 1. choose the sentence range whose span best matches the candidate
    covered = [
        s for s in sentences
        if s.end > cand.start + 0.15 and s.start < cand.end - 0.15
    ]
    if not covered:
        # fallback: nearest single sentence
        covered = [min(sentences, key=lambda s: abs(s.start - cand.start))]

    # trim awkward leading sentences / incomplete trailing sentences
    while len(covered) > 1 and starts_awkwardly(covered[0].text):
        covered = covered[1:]
    while len(covered) > 1 and looks_incomplete(covered[-1].text):
        covered = covered[:-1]

    start = covered[0].start
    end = covered[-1].end

    # 2. pull to inter-word silence so we never clip a word
    words = _all_words(sentences)
    gcut_s = _nearest_gap_cut(words, start, prefer="before")
    if gcut_s is not None and abs(gcut_s - start) < 1.2:
        start = gcut_s
    gcut_e = _nearest_gap_cut(words, end, prefer="after")
    if gcut_e is not None and abs(gcut_e - end) < 1.2:
        end = gcut_e

    # 3. apply padding, clamp to video
    start = max(0.0, start - pad)
    end = min(video_duration, end + pad)
    if end - start < settings.min_clip_seconds:
        end = min(video_duration, start + settings.min_clip_seconds)

    # 4. build caption segments limited to the window, re-based text
    seg_out: list[Segment] = []
    clean_sentences: list[str] = []
    for i, s in enumerate(covered):
        txt = s.text
        if i == 0:
            txt = strip_leading_filler(txt)
        clean_sentences.append(txt)
        ws = [w for w in s.words if w.end > start and w.start < end]
        seg_out.append(
            Segment(
                start=max(start, s.start),
                end=min(end, s.end),
                text=txt,
                words=ws,
            )
        )
    return round(start, 3), round(end, 3), seg_out, clean_sentences

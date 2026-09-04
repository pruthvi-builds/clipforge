"""STAGE E (part 1) — transparent, rule-based clip scores.

These run with no LLM and are always computed. When the LLM is available its
judgement is blended in (see :mod:`clipforge.scoring.combine`). Scores are 0-100
integers; we avoid fake precision by rounding to the nearest whole number and
clamping.
"""

from __future__ import annotations

from ..models import Candidate, ClipScore
from ..util.text import (
    feature_flags,
    filler_ratio,
    looks_incomplete,
    starts_awkwardly,
    word_count,
)


def _clamp(x: float) -> int:
    return int(max(0, min(100, round(x))))


def hook_score(text: str) -> int:
    first_sentence = text.strip().split(". ")[0]
    flags = feature_flags(first_sentence)
    s = 45.0
    if not starts_awkwardly(first_sentence):
        s += 15
    else:
        s -= 20
    if flags["question"]:
        s += 12
    if flags["strong_claim"]:
        s += 20
    if flags["number"]:
        s += 8
    if flags["emotion"]:
        s += 10
    if flags["contrast"]:
        s += 8
    wc = word_count(first_sentence)
    if 4 <= wc <= 22:
        s += 8
    elif wc > 34:
        s -= 12
    return _clamp(s)


def clarity_score(cand: Candidate) -> int:
    s = 78.0
    s -= 45 * filler_ratio(cand.text)
    wc = word_count(cand.text)
    wps = wc / max(1.0, cand.duration)
    if wps < 1.4:            # long pauses / dead air
        s -= 18
    elif wps > 3.6:          # rushed
        s -= 8
    if looks_incomplete(cand.text):
        s -= 15
    return _clamp(s)


def self_contained_score(cand: Candidate) -> int:
    s = 70.0
    low = cand.text.lower().strip()
    if starts_awkwardly(cand.text):
        s -= 18
    if low.startswith(("and ", "so ", "but ", "because ", "which ", "that ")):
        s -= 12
    # pronoun with no referent right at the top reads as "missing context"
    if low.split()[:1] and low.split()[0] in {"it", "they", "he", "she", "this", "that", "these", "those"}:
        s -= 14
    if looks_incomplete(cand.text):
        s -= 16
    if cand.text.strip().endswith((".", "!", "?")):
        s += 10
    if 90 <= word_count(cand.text) <= 240:
        s += 8
    return _clamp(s)


def emotion_score(text: str) -> int:
    f = feature_flags(text)
    s = 35.0
    if f["emotion"]:
        s += 30
    if f["story"]:
        s += 18
    if "!" in text:
        s += 6
    return _clamp(s)


def novelty_score(text: str) -> int:
    f = feature_flags(text)
    s = 40.0
    if f["strong_claim"]:
        s += 25
    if f["contrast"]:
        s += 15
    if f["number"]:
        s += 10
    low = text.lower()
    for phrase in ("nobody tells you", "most people", "the truth", "counterintuitive",
                   "surprising", "i was wrong", "turns out", "the secret"):
        if phrase in low:
            s += 8
    return _clamp(s)


def story_score(text: str) -> int:
    f = feature_flags(text)
    s = 30.0
    if f["story"]:
        s += 35
    low = text.lower()
    for phrase in ("i learned", "the biggest mistake", "here's what happened",
                   "i wish i knew", "when i started", "a few years ago"):
        if phrase in low:
            s += 10
    return _clamp(s)


def actionability_score(text: str) -> int:
    f = feature_flags(text)
    s = 30.0
    if f["actionable"]:
        s += 40
    if f["number"]:
        s += 8
    return _clamp(s)


def audio_quality_score(cand: Candidate, no_speech_prob: float, avg_logprob: float) -> int:
    s = 85.0
    s -= 120 * max(0.0, no_speech_prob - 0.2)
    if avg_logprob:
        s += 12 * (avg_logprob + 0.5)   # logprob near 0 is good
    return _clamp(s)


def engagement_score(parts: ClipScore) -> int:
    # engagement summarises the "will someone watch to the end" qualities
    s = (
        0.34 * parts.hook
        + 0.22 * parts.clarity
        + 0.16 * parts.novelty
        + 0.14 * parts.emotion
        + 0.14 * parts.self_contained
    )
    return _clamp(s)


def heuristic_score(
    cand: Candidate,
    *,
    no_speech_prob: float = 0.0,
    avg_logprob: float = 0.0,
) -> ClipScore:
    sc = ClipScore()
    sc.hook = hook_score(cand.text)
    sc.clarity = clarity_score(cand)
    sc.self_contained = self_contained_score(cand)
    sc.emotion = emotion_score(cand.text)
    sc.novelty = novelty_score(cand.text)
    sc.story = story_score(cand.text)
    sc.actionability = actionability_score(cand.text)
    sc.audio_quality = audio_quality_score(cand, no_speech_prob, avg_logprob)
    sc.engagement = engagement_score(sc)
    sc.overall = _clamp(
        0.30 * sc.engagement
        + 0.22 * sc.hook
        + 0.16 * sc.self_contained
        + 0.12 * sc.clarity
        + 0.10 * sc.novelty
        + 0.05 * sc.emotion
        + 0.05 * sc.audio_quality
    )
    return sc

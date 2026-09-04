"""STAGE B + C — rule-based seed detection and candidate window generation.

We deliberately do NOT ask an LLM to pick timestamps from a 2-hour transcript.
Instead:
  B) score every sentence with cheap lexical rules -> "seeds"
  C) around each strong seed, build several candidate windows (~15/20/30/45/60s),
     each snapped to sentence boundaries and given a little lead-in context.
The LLM later *evaluates* this short list (stage D).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..logging_setup import get_logger
from ..models import Candidate
from ..util.text import (
    feature_flags,
    filler_ratio,
    looks_incomplete,
    starts_awkwardly,
    word_count,
)
from .segment import TimedSentence

log = get_logger("clipforge.candidates")

_FEATURE_WEIGHTS = {
    "question": 1.4,
    "number": 1.6,
    "contrast": 1.5,
    "emotion": 1.7,
    "strong_claim": 2.2,
    "story": 2.0,
    "actionable": 1.8,
}

_TARGET_LENGTHS = [15.0, 20.0, 30.0, 45.0, 60.0]


@dataclass
class Seed:
    sentence: TimedSentence
    strength: float
    features: dict[str, bool]
    reason: str


def find_seeds(sentences: list[TimedSentence]) -> list[Seed]:
    seeds: list[Seed] = []
    for ts in sentences:
        wc = word_count(ts.text)
        if wc < 4:
            continue
        flags = feature_flags(ts.text)
        strength = 0.0
        hit: list[str] = []
        for name, on in flags.items():
            if on:
                strength += _FEATURE_WEIGHTS[name]
                hit.append(name)
        # a strong standalone opener is valuable even without lexical features
        if not starts_awkwardly(ts.text) and wc >= 8 and not looks_incomplete(ts.text):
            strength += 0.5
        # penalise filler-heavy or low-confidence ASR
        strength *= (1.0 - 0.6 * filler_ratio(ts.text))
        if ts.avg_logprob and ts.avg_logprob < -1.1:
            strength *= 0.7
        if strength >= 1.6:
            seeds.append(
                Seed(
                    sentence=ts,
                    strength=round(strength, 3),
                    features=flags,
                    reason=", ".join(hit) or "strong statement",
                )
            )
    seeds.sort(key=lambda s: s.strength, reverse=True)
    log.info("found %d seed sentences", len(seeds))
    return seeds


def _window_from_anchor(
    sentences: list[TimedSentence],
    anchor_idx: int,
    target: float,
    settings: Settings,
) -> tuple[int, int] | None:
    """Grow a sentence window around ``anchor_idx`` toward ``target`` seconds.

    Grows *backwards* first (context / setup) then forwards (payoff), staying in
    the same block where possible and never exceeding max_clip_seconds.
    """
    n = len(sentences)
    lo = hi = anchor_idx
    anchor_block = sentences[anchor_idx].block

    def dur() -> float:
        return sentences[hi].end - sentences[lo].start

    # a touch of lead-in context: include the previous sentence if it's close
    if lo > 0 and sentences[lo].gap_before < 0.9 and sentences[lo - 1].block == anchor_block:
        lo -= 1

    guard = 0
    while dur() < target and guard < 200:
        guard += 1
        grew = False
        # prefer extending forward to complete the thought
        if hi + 1 < n and sentences[hi + 1].block == anchor_block:
            if sentences[hi + 1].gap_before < 1.6:
                hi += 1
                grew = True
        if dur() < target and lo - 1 >= 0 and sentences[lo - 1].block == anchor_block:
            if sentences[lo].gap_before < 1.6:
                lo -= 1
                grew = True
        if not grew:
            break

    d = dur()
    if d < settings.min_clip_seconds or d > settings.max_clip_seconds:
        # allow slight overflow if we can trim a trailing sentence
        if d > settings.max_clip_seconds and hi > anchor_idx:
            hi -= 1
            d = dur()
        if d < settings.min_clip_seconds or d > settings.max_clip_seconds:
            return None

    # reject windows that start mid-thought or on filler unless we can nudge
    while lo < anchor_idx and starts_awkwardly(sentences[lo].text):
        lo += 1
    while hi > anchor_idx and looks_incomplete(sentences[hi].text):
        hi -= 1
    if hi < lo:
        return None
    if sentences[hi].end - sentences[lo].start < settings.min_clip_seconds:
        return None
    return lo, hi


def generate_candidates(
    sentences: list[TimedSentence],
    seeds: list[Seed],
    settings: Settings,
    *,
    max_seeds: int = 40,
) -> list[Candidate]:
    """Stage C: expand seeds into de-duplicated candidate windows."""
    by_index = {ts.index: ts for ts in sentences}
    seen: set[tuple[int, int]] = set()
    candidates: list[Candidate] = []

    lengths = _TARGET_LENGTHS
    forced = settings.default_clip_length
    if forced not in ("auto", "", None):
        try:
            lengths = [float(forced)]
        except ValueError:
            pass

    for seed in seeds[:max_seeds]:
        anchor = seed.sentence.index
        if anchor not in by_index:
            continue
        anchor_pos = [i for i, ts in enumerate(sentences) if ts.index == anchor][0]
        for target in lengths:
            win = _window_from_anchor(sentences, anchor_pos, target, settings)
            if not win:
                continue
            lo, hi = win
            key = (sentences[lo].index, sentences[hi].index)
            if key in seen:
                continue
            seen.add(key)
            text = " ".join(sentences[i].text for i in range(lo, hi + 1)).strip()
            candidates.append(
                Candidate(
                    start=sentences[lo].start,
                    end=sentences[hi].end,
                    text=text,
                    seed_reason=seed.reason,
                    features=seed.features,
                )
            )

    log.info("generated %d candidate windows", len(candidates))
    return candidates

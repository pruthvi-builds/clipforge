"""STAGE A — transcript segmentation.

Turns raw Whisper segments into a flat list of *timed sentences* (the unit the
rest of the pipeline reasons about) and groups them into *blocks* separated by
noticeable pauses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Transcript, Word
from ..util.text import split_sentences


@dataclass
class TimedSentence:
    index: int
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    block: int = 0
    # gap (silence) to the previous sentence, seconds
    gap_before: float = 0.0
    no_speech_prob: float = 0.0
    avg_logprob: float = 0.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def _sentence_time_from_words(words: list[Word], frag: str) -> tuple[float, float, list[Word]] | None:
    """Best-effort: map a sentence fragment to the words that compose it."""
    if not words:
        return None
    frag_tokens = [w for w in frag.lower().split() if w]
    if not frag_tokens:
        return None
    # slide a window over words matching token count (+/- 2)
    n = len(frag_tokens)
    best = None
    for i in range(len(words)):
        for span in (n, n - 1, n + 1, n - 2, n + 2):
            if span <= 0 or i + span > len(words):
                continue
            chunk = words[i:i + span]
            joined = " ".join(w.text.lower().strip(".,!?;:") for w in chunk)
            score = _similar(joined, " ".join(t.strip(".,!?;:") for t in frag_tokens))
            if best is None or score > best[0]:
                best = (score, chunk)
    if best and best[0] >= 0.55:
        chunk = best[1]
        return chunk[0].start, chunk[-1].end, chunk
    return None


def _similar(a: str, b: str) -> float:
    at, bt = set(a.split()), set(b.split())
    if not at or not bt:
        return 0.0
    return len(at & bt) / len(at | bt)


def build_timed_sentences(transcript: Transcript, *, block_gap: float = 1.2) -> list[TimedSentence]:
    """Produce a flat, globally-indexed list of timed sentences."""
    out: list[TimedSentence] = []
    idx = 0
    for seg in transcript.segments:
        sentences = split_sentences(seg.text)
        if not sentences:
            continue
        seg_words = seg.words
        if len(sentences) == 1:
            spans = [(seg.start, seg.end, seg_words)]
        else:
            spans = []
            cursor_time = seg.start
            for si, s in enumerate(sentences):
                mapped = _sentence_time_from_words(seg_words, s.text) if seg_words else None
                if mapped:
                    spans.append(mapped)
                    cursor_time = mapped[1]
                else:
                    # proportional split by character length
                    frac = len(s.text) / max(1, len(seg.text))
                    dur = seg.duration * frac
                    st = cursor_time
                    en = min(seg.end, st + dur) if si < len(sentences) - 1 else seg.end
                    spans.append((st, en, []))
                    cursor_time = en
        for (st, en, words), s in zip(spans, sentences):
            out.append(
                TimedSentence(
                    index=idx,
                    start=round(float(st), 3),
                    end=round(float(max(en, st + 0.2)), 3),
                    text=s.text.strip(),
                    words=list(words),
                    no_speech_prob=seg.no_speech_prob,
                    avg_logprob=seg.avg_logprob,
                )
            )
            idx += 1

    # assign blocks by inter-sentence gap
    block = 0
    for i, ts in enumerate(out):
        if i == 0:
            ts.gap_before = 0.0
        else:
            ts.gap_before = round(max(0.0, ts.start - out[i - 1].end), 3)
            if ts.gap_before >= block_gap:
                block += 1
        ts.block = block
    return out

from clipforge.clipdetect.segment import build_timed_sentences
from clipforge.clipdetect.candidates import find_seeds, generate_candidates
from clipforge.config import Settings


def test_timed_sentences_have_monotonic_times(sample_transcript):
    sents = build_timed_sentences(sample_transcript)
    assert len(sents) >= 10
    for a, b in zip(sents, sents[1:]):
        assert a.start <= a.end
        assert b.start >= a.start - 0.01


def test_seeds_find_the_obvious_hooks(sample_transcript):
    sents = build_timed_sentences(sample_transcript)
    seeds = find_seeds(sents)
    texts = " || ".join(s.sentence.text.lower() for s in seeds)
    assert "biggest mistake" in texts
    assert "nobody tells you" in texts
    # the greeting / sign-off should not be strong seeds
    top5 = [s.sentence.text.lower() for s in seeds[:5]]
    assert not any("thanks for tuning in" in t for t in top5)


def test_generate_candidates_respects_length_bounds(sample_transcript):
    s = Settings()
    s.min_clip_seconds = 10
    s.max_clip_seconds = 60
    sents = build_timed_sentences(sample_transcript)
    seeds = find_seeds(sents)
    cands = generate_candidates(sents, seeds, s)
    assert cands, "expected at least one candidate"
    for c in cands:
        assert 10 - 1e-6 <= c.duration <= 60 + 1e-6
        assert c.text.strip()


def test_candidates_are_deduplicated_by_sentence_span(sample_transcript):
    s = Settings()
    sents = build_timed_sentences(sample_transcript)
    seeds = find_seeds(sents)
    cands = generate_candidates(sents, seeds, s)
    spans = {(round(c.start, 2), round(c.end, 2)) for c in cands}
    assert len(spans) == len(cands)

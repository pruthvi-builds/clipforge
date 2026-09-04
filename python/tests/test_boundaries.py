from clipforge.clipdetect.segment import build_timed_sentences
from clipforge.clipdetect.boundaries import refine_boundaries
from clipforge.config import Settings
from clipforge.models import Candidate


def test_boundaries_snap_to_sentences_and_stay_in_video(sample_transcript):
    s = Settings()
    s.boundary_padding = 0.3
    sents = build_timed_sentences(sample_transcript)
    # rough window that starts/ends mid-sentence
    cand = Candidate(start=17.3, end=44.1, text="")
    start, end, segs, clean = refine_boundaries(
        cand, sents, s, video_duration=sample_transcript.duration
    )
    assert start >= 0
    assert end <= sample_transcript.duration + 1e-6
    assert start < end
    assert segs and clean
    # first clean sentence should not start with filler
    assert not clean[0].lower().startswith(("so ", "and ", "um "))


def test_boundaries_trim_incomplete_trailing_sentence(sample_transcript):
    s = Settings()
    sents = build_timed_sentences(sample_transcript)
    cand = Candidate(start=11.0, end=30.0, text="")
    start, end, segs, clean = refine_boundaries(
        cand, sents, s, video_duration=sample_transcript.duration
    )
    assert clean[-1].rstrip().endswith((".", "!", "?"))


def test_minimum_duration_enforced(sample_transcript):
    s = Settings()
    s.min_clip_seconds = 15
    sents = build_timed_sentences(sample_transcript)
    cand = Candidate(start=11.0, end=13.0, text="")
    start, end, *_ = refine_boundaries(
        cand, sents, s, video_duration=sample_transcript.duration
    )
    assert end - start >= 15 - 1e-6

from clipforge.models import Candidate, ClipScore
from clipforge.scoring.heuristics import heuristic_score, hook_score
from clipforge.scoring.combine import blend, length_penalty


def _cand(text, dur=32.0):
    return Candidate(start=0.0, end=dur, text=text)


def test_strong_hook_beats_weak_hook():
    strong = hook_score("The biggest mistake that cost me three years.")
    weak = hook_score("So anyway we kind of just kept going you know.")
    assert strong > weak
    assert 0 <= strong <= 100 and 0 <= weak <= 100


def test_full_heuristic_prefers_rich_content():
    good = heuristic_score(_cand(
        "The biggest mistake I made was hiring too fast. "
        "I spent three years building the wrong product. "
        "The lesson is simple: stay small until it works."
    ))
    filler = heuristic_score(_cand(
        "So um yeah like I mean you know we basically just sort of kept going and stuff."
    ))
    assert good.overall > filler.overall
    for field, val in good.to_dict().items():
        assert 0 <= val <= 100


def test_blend_without_llm_is_identity():
    h = ClipScore(overall=70, engagement=65, hook=80)
    out = blend(h, None)
    assert out.overall == 70 and out.engagement == 65


def test_blend_moves_toward_llm():
    h = ClipScore(overall=50, engagement=50)
    out = blend(h, 100, llm_weight=0.5)
    assert 70 <= out.overall <= 80


def test_length_penalty_bounds():
    assert length_penalty(90, 8) < 90
    assert length_penalty(90, 120) < 90
    assert length_penalty(80, 40) >= 80

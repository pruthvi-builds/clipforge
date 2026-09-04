import pytest

from clipforge.ai.schema import (
    loads_forgiving, validate_candidate_eval, validate_eval_batch, validate_hooks,
)
from clipforge.util.errors import LLMError


def test_loads_plain_json():
    assert loads_forgiving('{"a": 1}') == {"a": 1}


def test_loads_with_code_fence_and_prose():
    raw = 'Sure! Here is the result:\n```json\n{"score": 91}\n```\nHope that helps.'
    assert loads_forgiving(raw)["score"] == 91


def test_loads_repairs_trailing_comma_and_smart_quotes():
    raw = '{“hook”: “Nobody tells you this”, "score": 80,}'
    obj = loads_forgiving(raw)
    assert obj["score"] == 80
    assert obj["hook"].startswith("Nobody")


def test_loads_extracts_largest_blob():
    raw = 'garbage {} more {"results":[{"index":0,"score":77}]} trailing'
    obj = loads_forgiving(raw)
    assert obj["results"][0]["score"] == 77


def test_loads_raises_on_garbage():
    with pytest.raises(LLMError):
        loads_forgiving("not json at all, no braces")


def test_validate_candidate_eval_coerces_and_clamps():
    out = validate_candidate_eval({
        "score": "150", "hook": '  "Big claim"  ', "category": "nonsense",
        "self_contained": "true", "emphasis_words": ["WRONG", "", "THREE YEARS", 5],
    })
    assert out["score"] == 100
    assert out["hook"] == "Big claim"
    assert out["category"] == "insight"
    assert out["self_contained"] is True
    # non-string emphasis entries are dropped
    assert out["emphasis_words"] == ["WRONG", "THREE YEARS"]


def test_validate_eval_batch_by_index():
    obj = {"results": [
        {"index": 1, "score": 60, "category": "story"},
        {"index": 0, "score": 90, "category": "advice"},
    ]}
    rows = validate_eval_batch(obj, 2)
    assert rows[0]["score"] == 90
    assert rows[1]["score"] == 60


def test_validate_eval_batch_positional_fallback():
    obj = [{"score": 10, "category": "story"}, {"score": 20, "category": "advice"}]
    rows = validate_eval_batch(obj, 2)
    assert [r["score"] for r in rows] == [10, 20]


def test_validate_hooks():
    h = validate_hooks({"hook": "A", "altHook": "B", "openingText": "C"})
    assert h == {"hook": "A", "alt_hook": "B", "opening_text": "C"}

"""JSON parsing, repair and validation for local-LLM output.

Local models frequently wrap JSON in prose or code fences, or emit trailing
commas / single quotes. We try, in order:
  1. json.loads
  2. extract the largest {...} / [...] block and retry
  3. light repairs (fences, trailing commas, smart quotes) and retry
Then we *validate* against a hand-rolled schema (no jsonschema dependency) and
coerce types. Anything still invalid raises so the caller can fall back to
heuristics.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..util.errors import LLMError

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _largest_json_blob(text: str) -> str | None:
    best = None
    for open_c, close_c in (("{", "}"), ("[", "]")):
        depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == open_c:
                if depth == 0:
                    start = i
                depth += 1
            elif ch == close_c and depth:
                depth -= 1
                if depth == 0 and start >= 0:
                    blob = text[start:i + 1]
                    if best is None or len(blob) > len(best):
                        best = blob
    return best


def loads_forgiving(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        raise LLMError("Empty LLM response.")

    attempts: list[str] = [text]
    m = _FENCE_RE.search(text)
    if m:
        attempts.append(m.group(1).strip())
    blob = _largest_json_blob(text)
    if blob:
        attempts.append(blob)

    for attempt in attempts:
        for candidate in (attempt, _repair(attempt)):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    raise LLMError("Could not parse JSON from the local model's response.")


def _repair(s: str) -> str:
    s = s.strip().strip("`")
    s = _TRAILING_COMMA_RE.sub(r"\1", s)
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    # bare single-quoted keys/strings -> double (best effort, only if no dquotes)
    if '"' not in s and "'" in s:
        s = s.replace("'", '"')
    return s


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def _num(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, f))


def _clean_str(v: Any, max_len: int = 240) -> str:
    if not isinstance(v, str):
        return ""
    return v.strip().strip('"').replace("\n", " ")[:max_len]


VALID_CATEGORIES = {
    "story", "lesson", "insight", "surprising insight", "advice", "opinion",
    "question", "statistic", "emotional", "contrarian", "how-to", "definition",
}


def validate_candidate_eval(obj: Any) -> dict:
    """Coerce one LLM candidate-evaluation object into a safe dict."""
    if not isinstance(obj, dict):
        raise LLMError("Expected a JSON object for candidate evaluation.")
    cat = _clean_str(obj.get("category"), 40).lower() or "insight"
    if cat not in VALID_CATEGORIES:
        cat = "insight"
    return {
        "score": int(_num(obj.get("score"), 0, 100, 50)),
        "hook": _clean_str(obj.get("hook"), 90),
        "alt_hook": _clean_str(obj.get("alt_hook") or obj.get("altHook"), 90),
        "opening_text": _clean_str(obj.get("opening_text") or obj.get("openingText"), 60),
        "category": cat,
        "reason": _clean_str(obj.get("reason"), 240),
        "self_contained": bool(
            obj.get("self_contained", obj.get("selfContained", True))
        ),
        "emphasis_words": [
            _clean_str(w, 32)
            for w in (obj.get("emphasis_words") or obj.get("emphasisWords") or [])
            if _clean_str(w, 32)
        ][:8],
    }


def validate_eval_batch(obj: Any, n_expected: int) -> list[dict | None]:
    """Parse a batch response: ``{"results":[{index, ...}, ...]}`` or a bare list."""
    if isinstance(obj, dict):
        rows = obj.get("results") or obj.get("candidates") or obj.get("clips") or []
    elif isinstance(obj, list):
        rows = obj
    else:
        raise LLMError("Unexpected batch shape from LLM.")

    out: list[dict | None] = [None] * n_expected
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("index", row.get("id", -1)))
        except (TypeError, ValueError):
            idx = -1
        try:
            parsed = validate_candidate_eval(row)
        except LLMError:
            continue
        if 0 <= idx < n_expected:
            out[idx] = parsed
    # if the model ignored indices but returned the right count in order
    if all(v is None for v in out) and len(rows) == n_expected:
        for i, row in enumerate(rows):
            try:
                out[i] = validate_candidate_eval(row)
            except LLMError:
                out[i] = None
    return out


def validate_hooks(obj: Any) -> dict:
    if not isinstance(obj, dict):
        raise LLMError("Expected an object for hook generation.")
    return {
        "hook": _clean_str(obj.get("hook"), 90),
        "alt_hook": _clean_str(obj.get("alt_hook") or obj.get("altHook"), 90),
        "opening_text": _clean_str(obj.get("opening_text") or obj.get("openingText"), 60),
    }

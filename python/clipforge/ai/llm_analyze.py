"""STAGE D — local-LLM evaluation of the rule-based candidate short-list.

Everything here degrades gracefully: if Ollama is missing, the model is not
pulled, or the response can't be repaired into valid JSON after retries, the
caller simply keeps the heuristic scores.
"""

from __future__ import annotations

from ..config import Settings
from ..logging_setup import get_logger
from ..models import Candidate
from ..util.errors import LLMError
from .ollama_client import OllamaClient
from .prompts import CANDIDATE_EVAL_SYSTEM, CANDIDATE_EVAL_USER
from .schema import loads_forgiving, validate_eval_batch

log = get_logger("clipforge.llm")

_BATCH = 6          # candidates per LLM call (keeps prompts small for 7B models)
_RETRIES = 2


class LLMAnalyzer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OllamaClient(settings.ollama_base_url)
        self._checked: bool | None = None

    def available(self) -> tuple[bool, str]:
        if not self.client.ping():
            return False, f"Ollama not reachable at {self.settings.ollama_base_url}"
        if not self.client.has_model(self.settings.model_name):
            return False, (
                f"Model {self.settings.model_name!r} is not installed. "
                f"Run: ollama pull {self.settings.model_name}"
            )
        return True, "ok"

    def _eval_batch(self, batch: list[Candidate], topic_hint: str) -> list[dict | None]:
        listing = "\n\n".join(
            f"[{i}] ({c.duration:.0f}s) {c.text}" for i, c in enumerate(batch)
        )
        user = CANDIDATE_EVAL_USER.format(
            topic_hint=topic_hint or "unknown", n=len(batch), candidates=listing
        )
        last_err = "unknown"
        for attempt in range(_RETRIES + 1):
            try:
                raw = self.client.chat_json(
                    model=self.settings.model_name,
                    system=CANDIDATE_EVAL_SYSTEM,
                    user=user if attempt == 0 else user + "\n\nReturn valid JSON only.",
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                )
                obj = loads_forgiving(raw)
                return validate_eval_batch(obj, len(batch))
            except LLMError as e:
                last_err = str(e)
                log.warning("LLM batch attempt %d failed: %s", attempt + 1, e)
        log.warning("LLM batch giving up after retries: %s", last_err)
        return [None] * len(batch)

    def evaluate(
        self,
        candidates: list[Candidate],
        *,
        topic_hint: str = "",
        progress=None,
    ) -> list[Candidate]:
        """Attach LLM fields to candidates in place; return the same list.

        Adds ``.score`` overrides via ``_llm_overall`` attribute used by the
        scoring blend step, plus hook/category/reason/emphasis.
        """
        ok, reason = self.available()
        if not ok:
            log.info("LLM analysis skipped: %s", reason)
            for c in candidates:
                c.llm_used = False
            return candidates

        total = max(1, len(candidates))
        consecutive_batch_failures = 0
        for start in range(0, len(candidates), _BATCH):
            batch = candidates[start:start + _BATCH]
            if consecutive_batch_failures >= 2:
                # Ollama answered the initial ping but is now unresponsive
                # under load — every remaining batch would otherwise pay the
                # same multi-minute retry cost for no benefit. Stop calling
                # it and let the rest keep their heuristic scores.
                log.warning(
                    "LLM unresponsive for %d consecutive batches — skipping "
                    "remaining %d candidate(s), keeping heuristic scores",
                    consecutive_batch_failures, len(candidates) - start,
                )
                for c in candidates[start:]:
                    c.llm_used = False
                break
            results = self._eval_batch(batch, topic_hint)
            consecutive_batch_failures = (
                0 if any(results) else consecutive_batch_failures + 1
            )
            for c, res in zip(batch, results):
                if not res:
                    c.llm_used = False
                    continue
                c.llm_used = True
                c._llm_overall = res["score"]  # type: ignore[attr-defined]
                c.hook = res["hook"] or c.hook
                c.alt_hook = res["alt_hook"] or c.alt_hook
                c.opening_text = res["opening_text"] or c.opening_text
                c.category = res["category"] or c.category
                c.reason = res["reason"] or c.reason
                c.self_contained = res["self_contained"]
                if res["emphasis_words"]:
                    c.emphasis_words = res["emphasis_words"]
            if progress:
                progress(min(1.0, (start + len(batch)) / total), "Scoring moments with local AI")
        return candidates

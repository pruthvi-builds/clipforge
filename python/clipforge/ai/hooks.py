"""STAGE 12 — hook / title / opening-text generation with graceful fallback.

If the LLM already produced a faithful hook during candidate evaluation we keep
it. Otherwise we optionally ask the LLM for one; if that fails or is disabled we
derive a hook from the clip's own first sentence (never invented).
"""

from __future__ import annotations

from ..config import Settings
from ..logging_setup import get_logger
from ..models import Clip
from ..util.errors import LLMError
from ..util.text import split_sentences, strip_leading_filler
from .ollama_client import OllamaClient
from .prompts import HOOK_SYSTEM, HOOK_USER
from .schema import loads_forgiving, validate_hooks

log = get_logger("clipforge.hooks")


def _fallback_hook(text: str) -> tuple[str, str, str]:
    sents = split_sentences(text)
    first = strip_leading_filler(sents[0].text) if sents else text.strip()
    first = first.rstrip(".")
    hook = first if len(first) <= 60 else first[:57].rsplit(" ", 1)[0] + "…"
    alt = ""
    if len(sents) > 1:
        s2 = strip_leading_filler(sents[1].text).rstrip(".")
        alt = s2 if len(s2) <= 60 else s2[:57].rsplit(" ", 1)[0] + "…"
    opening = hook if len(hook) <= 40 else hook[:37].rsplit(" ", 1)[0] + "…"
    return hook, alt, opening


def generate_hook(
    clip: Clip,
    settings: Settings,
    *,
    use_ai: bool | None = None,
) -> Clip:
    use_ai = settings.use_ai_hooks if use_ai is None else use_ai

    if clip.hook and clip.llm_used:
        # already have a faithful LLM hook from stage D
        if not clip.opening_text:
            clip.opening_text = _fallback_hook(clip.text)[2]
        return clip

    if use_ai:
        client = OllamaClient(settings.ollama_base_url)
        if client.ping() and client.has_model(settings.model_name):
            try:
                raw = client.chat_json(
                    model=settings.model_name,
                    system=HOOK_SYSTEM,
                    user=HOOK_USER.format(excerpt=clip.text[:1200], category=clip.category),
                    temperature=min(0.6, settings.llm_temperature + 0.2),
                    max_tokens=200,
                )
                h = validate_hooks(loads_forgiving(raw))
                if h["hook"]:
                    clip.hook = h["hook"]
                    clip.alt_hook = h["alt_hook"] or clip.alt_hook
                    clip.opening_text = h["opening_text"] or clip.opening_text
                    return clip
            except LLMError as e:
                log.info("hook LLM fallback (%s)", e)

    hook, alt, opening = _fallback_hook(clip.text)
    clip.hook = clip.hook or hook
    clip.alt_hook = clip.alt_hook or alt
    clip.opening_text = clip.opening_text or opening
    return clip

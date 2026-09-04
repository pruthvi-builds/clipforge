"""Prompt templates for the local LLM. Kept in one place so they're easy to tune."""

from __future__ import annotations

CANDIDATE_EVAL_SYSTEM = """\
You are an expert short-form video editor (YouTube Shorts, Reels, TikTok).
You are given several CANDIDATE excerpts taken from one long video's transcript.
For EACH candidate, judge how well it would work as a standalone short clip.

Prefer moments with:
- a strong opening line that creates curiosity
- enough context to make sense on their own
- a useful insight, a story, tension, surprise, or an emotional payoff
- a clear, memorable ending

Penalise:
- greetings, housekeeping, sponsor reads, introductions
- filler and repetition
- incomplete thoughts
- statements that only make sense with missing context

Rules:
- Return JSON ONLY. No prose, no markdown.
- NEVER invent facts that are not in the transcript text.
- hook and opening_text must be faithful to what is actually said.
- score is 0-100 for overall short-form potential.
- category is one of: story, lesson, insight, advice, opinion, question,
  statistic, emotional, contrarian, how-to, definition.
- emphasis_words: 0-6 words already present in the excerpt that deserve
  on-screen emphasis.

Output shape:
{"results":[
  {"index":0,"score":0-100,"hook":"...","alt_hook":"...","opening_text":"...",
   "category":"...","reason":"one sentence","self_contained":true,
   "emphasis_words":["..."]}
]}
"""

CANDIDATE_EVAL_USER = """\
Video topic hint: {topic_hint}

Evaluate these {n} candidates. Return one result object per index.

{candidates}
"""

HOOK_SYSTEM = """\
You write short, punchy titles/hooks for short-form videos.
Given a transcript excerpt, produce:
- hook: <= 60 chars, faithful to the excerpt, no clickbait that isn't supported
- alt_hook: a different angle, same faithfulness rule
- opening_text: <= 40 chars, on-screen text for the first second

Return JSON ONLY: {"hook":"...","alt_hook":"...","opening_text":"..."}
Never invent facts not present in the excerpt.
"""

HOOK_USER = """\
Excerpt:
\"\"\"{excerpt}\"\"\"

Category: {category}
"""

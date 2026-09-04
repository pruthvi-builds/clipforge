"""Pure-Python text utilities: sentence splitting, filler detection, keywording.

No NLTK / spaCy dependency — a carefully tuned regex splitter is good enough for
transcript text and keeps the install tiny and offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Abbreviations that must NOT end a sentence.
_ABBREV = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e",
    "inc", "ltd", "co", "corp", "u.s", "u.k", "a.m", "p.m", "no", "vol", "fig",
}

_SENT_END = re.compile(r"([.!?]+)(\s+|$)")
_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_FILLER_RE = re.compile(
    r"\b(um+|uh+|erm+|hmm+|like|you know|i mean|sort of|kind of|basically|"
    r"literally|actually|so yeah|right\?)\b",
    re.IGNORECASE,
)
_LEADING_FILLER = re.compile(
    r"^\s*(so|and|but|um+|uh+|like|okay|ok|well|yeah|right|anyway|now)\b[\s,]*",
    re.IGNORECASE,
)

_NUMERIC_RE = re.compile(r"\b(\d[\d,\.]*)\s?(%|percent|x|times|years?|months?|days?|"
                         r"hours?|minutes?|dollars?|k|million|billion|thousand)?\b",
                         re.IGNORECASE)

_QUESTION_RE = re.compile(r"\b(why|how|what|when|where|who|which|would you|did you|"
                          r"have you|are you|is it|can you)\b", re.IGNORECASE)

_CONTRAST_RE = re.compile(r"\b(but|however|although|though|instead|whereas|"
                          r"on the other hand|turns out|in reality|actually)\b",
                          re.IGNORECASE)

_EMOTION_WORDS = {
    "love", "hate", "fear", "afraid", "scared", "amazing", "incredible",
    "terrible", "awful", "shocked", "surprised", "unbelievable", "insane",
    "crazy", "painful", "heartbreaking", "proud", "ashamed", "excited",
    "furious", "devastated", "thrilled", "grateful", "regret", "worst", "best",
}

_STRONG_CLAIM_RE = re.compile(
    r"\b(never|always|nobody|no one|"
    r"every(?:one|body) (?:knows|thinks|says|believes|wants|does|has|is)|"
    r"the (biggest|worst|best|only)|"
    r"the truth is|the reality is|the secret|here's the thing|the key|"
    r"most people (don't|think)|the mistake|what nobody tells you|"
    r"i guarantee|the number one)\b",
    re.IGNORECASE,
)

_STORY_RE = re.compile(
    r"\b(i (was|had|made|went|remember|realised|realized|learned|learnt|started|"
    r"decided|failed|quit|lost|found|built|tried)|when i|back (then|in)|one day|"
    r"a few years ago|the first time|it happened|here's what happened)\b",
    re.IGNORECASE,
)

_ACTION_RE = re.compile(
    r"\b(you should|you need to|you have to|the trick is|do this|try this|"
    r"start by|make sure|the way to|step one|first,|here's how|my advice)\b",
    re.IGNORECASE,
)


@dataclass
class Sentence:
    text: str
    start_char: int
    end_char: int


def split_sentences(text: str) -> list[Sentence]:
    """Split ``text`` into sentences, keeping character offsets.

    Handles the common abbreviation false-positives and keeps trailing
    punctuation attached to the sentence it belongs to.
    """
    text = text.strip()
    if not text:
        return []
    out: list[Sentence] = []
    start = 0
    for m in _SENT_END.finditer(text):
        end = m.end(1)
        chunk = text[start:end].strip()
        if not chunk:
            start = m.end()
            continue
        # abbreviation guard: last token before the period
        last_word = re.findall(r"[A-Za-z.]+", chunk[-8:].lower())
        if last_word and last_word[-1].rstrip(".") in _ABBREV and m.group(1) == ".":
            continue
        out.append(Sentence(chunk, start, end))
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(Sentence(tail, start, len(text)))
    return out


def tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def filler_ratio(text: str) -> float:
    words = word_count(text)
    if words == 0:
        return 1.0
    fillers = len(_FILLER_RE.findall(text))
    return min(1.0, fillers / max(1, words) * 3.0)


def starts_awkwardly(text: str) -> bool:
    """True if the sentence opens with a conjunction / filler that reads badly
    as the first line of a short clip."""
    return bool(_LEADING_FILLER.match(text.strip()))


def strip_leading_filler(text: str) -> str:
    return _LEADING_FILLER.sub("", text.strip(), count=1).strip() or text.strip()


def looks_incomplete(text: str) -> bool:
    """Heuristic: sentence probably cut mid-thought."""
    t = text.strip()
    if not t:
        return True
    if not re.search(r"[.!?]['\"]?$", t):
        return True
    if re.search(r"\b(and|or|but|because|so|the|a|an|to|of|with|that|which)$",
                 t.rstrip(".!?").lower()):
        return True
    return False


# --- feature detectors used by rule-based candidate detection -------------

def feature_flags(text: str) -> dict[str, bool]:
    return {
        "question": bool(text.strip().endswith("?")) or bool(_QUESTION_RE.search(text)),
        "number": bool(_NUMERIC_RE.search(text)),
        "contrast": bool(_CONTRAST_RE.search(text)),
        "emotion": any(w in _EMOTION_WORDS for w in tokenize(text)),
        "strong_claim": bool(_STRONG_CLAIM_RE.search(text)),
        "story": bool(_STORY_RE.search(text)),
        "actionable": bool(_ACTION_RE.search(text)),
    }


_STOPWORDS = set("""
a an the and or but if then else of to in on at by for with without from as is are was were
be been being it its this that these those i you he she they we me him her them us my your our
their his so not no yes do does did done have has had can could would should will shall may might
just really very much more most some any all one two three what when where who why how which than
about into over under out up down off again here there
""".split())


def keywords(text: str, limit: int = 6) -> list[str]:
    """Rough content keywords for a caption highlight fallback."""
    counts: dict[str, int] = {}
    for w in tokenize(text):
        if len(w) < 4 or w in _STOPWORDS:
            continue
        counts[w] = counts.get(w, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0])))
    return [w for w, _ in ranked[:limit]]

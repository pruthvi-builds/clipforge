"""Burned-in caption generation as ASS subtitles (rendered by FFmpeg libass).

Fully local, no commercial caption library. Supports word-level timing when the
transcript has it (grouping into 1-5 word cues with the active word emphasised)
and degrades to segment-level cues when it doesn't.

Five styles: clean | bold | karaoke | minimal | highlight.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import Segment, Word

CAPTION_STYLES = ("clean", "bold", "karaoke", "minimal", "highlight")


# --------------------------------------------------------------------------
# Options
# --------------------------------------------------------------------------
@dataclass
class CaptionOptions:
    style: str = "bold"
    play_w: int = 1080
    play_h: int = 1920
    font: str = "Arial"
    # font size is expressed for a 1920-tall canvas; scaled if canvas differs
    font_size: int = 0                 # 0 -> style default
    primary_color: str = "#FFFFFF"
    highlight_color: str = "#FFE14D"   # active / emphasised word
    outline_color: str = "#000000"
    box_color: str = "#111111"
    position: str = "bottom"           # bottom | center | top
    margin_v: int = 0                  # 0 -> style default (px from that edge)
    uppercase: bool | None = None      # None -> style default
    max_words: int = 0                 # 0 -> style default
    highlight_words: list[str] = field(default_factory=list)
    animate: bool = True


_STYLE_DEFAULTS = {
    #                 size  upper  words  margin  bold  outline shadow  boxed
    "clean":     dict(size=74,  upper=False, words=3, margin=300, bold=0, outline=3.2, shadow=0, boxed=False),
    "bold":      dict(size=96,  upper=True,  words=3, margin=330, bold=1, outline=5.0, shadow=2,  boxed=False),
    "karaoke":   dict(size=84,  upper=True,  words=4, margin=320, bold=1, outline=4.0, shadow=1,  boxed=False),
    "minimal":   dict(size=58,  upper=False, words=5, margin=230, bold=0, outline=2.0, shadow=0,  boxed=False),
    "highlight": dict(size=90,  upper=True,  words=3, margin=330, bold=1, outline=2.0, shadow=0,  boxed=True),
}

_PUNCT_RE = re.compile(r"[^\w']+", re.UNICODE)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _hex_to_ass(color: str, alpha: str = "00") -> str:
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        c = "FFFFFF"
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"&H{alpha}{b}{g}{r}".upper()


def _ass_time(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    cs = int(round((s - int(s)) * 100))
    s = int(s)
    if cs == 100:
        cs = 0
        s += 1
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _norm(w: str) -> str:
    return _PUNCT_RE.sub("", w or "").lower()


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


@dataclass
class _Cue:
    start: float
    end: float
    words: list[Word]


# --------------------------------------------------------------------------
# cue construction
# --------------------------------------------------------------------------
def _cues_from_words(words: list[Word], max_words: int, clip_start: float) -> list[_Cue]:
    cues: list[_Cue] = []
    bucket: list[Word] = []

    def flush():
        nonlocal bucket
        if not bucket:
            return
        st = max(0.0, bucket[0].start - clip_start)
        en = max(st + 0.2, bucket[-1].end - clip_start)
        cues.append(_Cue(st, en, list(bucket)))
        bucket = []

    for i, w in enumerate(words):
        if not w.text.strip():
            continue
        if bucket:
            gap = w.start - bucket[-1].end
            span = (w.end - bucket[0].start)
            ends_sentence = bool(re.search(r"[.!?]$", bucket[-1].text))
            if len(bucket) >= max_words or gap > 0.7 or span > 2.8 or ends_sentence:
                flush()
        bucket.append(w)
    flush()

    # stretch each cue slightly toward the next so captions don't flicker off
    for i, c in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else c.end + 0.4
        c.end = min(nxt - 0.02, c.end + 0.35)
        if c.end <= c.start:
            c.end = c.start + 0.25
    return cues


def _cues_from_segments(segments: list[Segment], max_words: int, clip_start: float) -> list[_Cue]:
    cues: list[_Cue] = []
    for seg in segments:
        tokens = [t for t in re.split(r"\s+", seg.text.strip()) if t]
        if not tokens:
            continue
        st = max(0.0, seg.start - clip_start)
        en = max(st + 0.3, seg.end - clip_start)
        n_chunks = max(1, (len(tokens) + max_words - 1) // max_words)
        chunk_dur = (en - st) / n_chunks
        for ci in range(n_chunks):
            chunk = tokens[ci * max_words:(ci + 1) * max_words]
            if not chunk:
                continue
            cs = st + ci * chunk_dur
            ce = cs + chunk_dur
            ws = []
            wdur = (ce - cs) / len(chunk)
            for wi, tok in enumerate(chunk):
                ws.append(Word(start=cs + wi * wdur, end=cs + (wi + 1) * wdur, text=tok))
            cues.append(_Cue(cs, ce, ws))
    return cues


# --------------------------------------------------------------------------
# dialogue rendering per style
# --------------------------------------------------------------------------
def _render_cue(cue: _Cue, opt: CaptionOptions, d: dict, hl_set: set[str]) -> list[str]:
    prim = _hex_to_ass(opt.primary_color)
    hl = _hex_to_ass(opt.highlight_color)
    scale = opt.play_h / 1920.0
    lines: list[str] = []

    def word_text(w: str) -> str:
        w = _esc(w)
        return w.upper() if (opt.uppercase if opt.uppercase is not None else d["upper"]) else w

    fade = "\\fad(90,60)" if opt.animate else ""

    if opt.style == "karaoke":
        # progressive fill: secondary colour -> primary as each word "plays"
        parts = []
        for w in cue.words:
            k = max(6, int(round((w.end - w.start) * 100)))
            emph = _norm(w.text) in hl_set
            col = f"\\c{hl}" if emph else f"\\c{prim}"
            parts.append(f"{{\\kf{k}{col}}}{word_text(w.text)}")
        body = " ".join(parts)
        lines.append(_dialogue(cue.start, cue.end, f"{{{fade}}}{body}"))
        return lines

    if opt.style in ("bold", "highlight", "clean", "minimal"):
        # one Dialogue per active word so the active word can be emphasised
        # while the rest of the cue stays visible.
        for i, active in enumerate(cue.words):
            seg_start = max(cue.start, active.start - (0.0 if opt.style != "clean" else 0.0))
            seg_end = active.end if i + 1 < len(cue.words) else cue.end
            seg_end = min(cue.end, max(seg_start + 0.08, seg_end))
            chunks = []
            for j, w in enumerate(cue.words):
                t = word_text(w.text)
                is_active = (j == i)
                is_emph = _norm(w.text) in hl_set
                if opt.style == "highlight" and (is_active or is_emph):
                    chunks.append(f"{{\\1c{hl}}}{t}{{\\1c{prim}}}")
                elif opt.style == "bold" and is_active:
                    pop = "\\fscx112\\fscy112" if opt.animate else ""
                    chunks.append(f"{{\\1c{hl}{pop}}}{t}{{\\1c{prim}\\fscx100\\fscy100}}")
                elif opt.style == "bold" and is_emph:
                    chunks.append(f"{{\\1c{hl}}}{t}{{\\1c{prim}}}")
                elif opt.style in ("clean", "minimal") and is_emph:
                    chunks.append(f"{{\\1c{hl}}}{t}{{\\1c{prim}}}")
                else:
                    chunks.append(t)
            body = " ".join(chunks)
            fx = fade if i == 0 else ""
            lines.append(_dialogue(seg_start, seg_end, f"{{{fx}}}{body}" if fx else body))
        return lines

    # fallback
    body = " ".join(word_text(w.text) for w in cue.words)
    lines.append(_dialogue(cue.start, cue.end, body))
    return lines


def _dialogue(start: float, end: float, text: str) -> str:
    return f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},CF,,0,0,0,,{text}"


# --------------------------------------------------------------------------
# public
# --------------------------------------------------------------------------
def build_ass(
    segments: list[Segment],
    opt: CaptionOptions,
    *,
    clip_start: float = 0.0,
    has_word_timestamps: bool = True,
    opening_text: str = "",
) -> str:
    style = opt.style if opt.style in CAPTION_STYLES else "bold"
    opt.style = style
    d = _STYLE_DEFAULTS[style]

    size = opt.font_size or d["size"]
    size = int(round(size * (opt.play_h / 1920.0)))
    margin_v = opt.margin_v or d["margin"]
    margin_v = int(round(margin_v * (opt.play_h / 1920.0)))
    align = {"bottom": 2, "center": 5, "top": 8}.get(opt.position, 2)
    border_style = 3 if d["boxed"] else 1

    prim = _hex_to_ass(opt.primary_color)
    out = _hex_to_ass(opt.outline_color)
    box = _hex_to_ass(opt.box_color, alpha="14")
    back = box if d["boxed"] else _hex_to_ass("#000000", alpha="A0")

    hl_set = {_norm(w) for w in opt.highlight_words if _norm(w)}

    # collect words
    all_words: list[Word] = []
    for s in segments:
        all_words.extend(w for w in s.words if w.text.strip())

    max_words = opt.max_words or d["words"]
    if has_word_timestamps and len(all_words) >= 2:
        cues = _cues_from_words(all_words, max_words, clip_start)
    else:
        cues = _cues_from_segments(segments, max_words, clip_start)

    header = f"""[Script Info]
; ClipForge captions
ScriptType: v4.00+
PlayResX: {opt.play_w}
PlayResY: {opt.play_h}
ScaledBorderAndShadow: yes
WrapStyle: 2
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CF,{opt.font},{size},{prim},{_hex_to_ass(opt.highlight_color)},{out},{back},{d['bold']},0,0,0,100,100,0.6,0,{border_style},{d['outline']},{d['shadow']},{align},90,90,{margin_v},1
Style: CFopen,{opt.font},{int(size*0.9)},{_hex_to_ass(opt.highlight_color)},{prim},{out},{back},1,0,0,0,100,100,1,0,1,4,1,8,80,80,{int(opt.play_h*0.14)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    body_lines: list[str] = []

    if opening_text.strip():
        anim = "\\fad(120,150)\\t(0,220,\\fscx108\\fscy108)\\t(220,360,\\fscx100\\fscy100)" if opt.animate else "\\fad(120,150)"
        body_lines.append(
            f"Dialogue: 0,{_ass_time(0.0)},{_ass_time(2.6)},CFopen,,0,0,0,,{{{anim}}}{_esc(opening_text.strip())}"
        )

    for cue in cues:
        body_lines.extend(_render_cue(cue, opt, d, hl_set))

    return header + "\n".join(body_lines) + "\n"

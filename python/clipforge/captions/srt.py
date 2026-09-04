"""Plain SRT export (segment-level). Useful as a downloadable sidecar."""

from __future__ import annotations

from ..models import Segment


def _ts(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(segments: list[Segment], *, clip_start: float = 0.0) -> str:
    lines: list[str] = []
    idx = 1
    for seg in segments:
        st = max(0.0, seg.start - clip_start)
        en = max(st + 0.2, seg.end - clip_start)
        text = seg.text.strip()
        if not text:
            continue
        lines.append(str(idx))
        lines.append(f"{_ts(st)} --> {_ts(en)}")
        lines.append(text)
        lines.append("")
        idx += 1
    return "\n".join(lines).strip() + "\n"

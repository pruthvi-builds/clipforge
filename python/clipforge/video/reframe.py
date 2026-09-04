"""Turn a face track into a smooth, time-varying crop window.

Output is a list of ``CropKey`` (t, x) where ``x`` is the left edge (pixels) of a
portrait crop of width ``crop_w`` taken from the source. The renderer feeds these
to FFmpeg via a ``sendcmd`` script so the crop glides instead of jumping.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..logging_setup import get_logger
from ..models import VideoMeta
from .frames import FaceObservation

log = get_logger("clipforge.reframe")


@dataclass
class CropPlan:
    crop_w: int
    crop_h: int
    keys: list[tuple[float, int]]         # (t_relative_to_clip, x_left_px)
    static: bool
    mode: str
    y_top: int = 0
    fit: bool = False                     # letterbox/pillarbox the whole frame, no crop


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _ema_smooth(values: list[float], alpha: float = 0.18) -> list[float]:
    if not values:
        return values
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    # second pass backwards to remove lag
    for i in range(len(out) - 2, -1, -1):
        out[i] = 0.6 * out[i] + 0.4 * out[i + 1]
    return out


def _limit_velocity(xs: list[float], max_step: float) -> list[float]:
    if not xs:
        return xs
    out = [xs[0]]
    for x in xs[1:]:
        prev = out[-1]
        dx = _clamp(x - prev, -max_step, max_step)
        out.append(prev + dx)
    return out


def plan_crop(
    meta: VideoMeta,
    clip_start: float,
    clip_end: float,
    observations: list[FaceObservation],
    *,
    mode: str = "smart_auto",
    out_w: int = 1080,
    out_h: int = 1920,
    tracking_margin: float = 1.9,
) -> CropPlan:
    """Compute the crop plan for one clip.

    ``tracking_margin`` widens the crop relative to face size so the speaker
    isn't cropped tight; larger = safer / calmer.
    """
    src_w, src_h = meta.width, meta.height
    target_ar = out_w / out_h                      # 0.5625 for 1080x1920
    src_ar = src_w / src_h if src_h else target_ar

    # fit: keep the whole source frame, letterbox/pillarbox instead of cropping.
    if mode == "fit":
        return CropPlan(src_w, src_h, [(0.0, 0)], static=True, mode="fit", y_top=0, fit=True)

    # Case 1: source already portrait-or-square -> no horizontal pan needed.
    if src_ar <= target_ar + 1e-3:
        crop_w = src_w
        crop_h = min(src_h, int(round(src_w / target_ar)))
        y_top = max(0, (src_h - crop_h) // 2)
        return CropPlan(crop_w, crop_h, [(0.0, 0)], static=True, mode="center", y_top=y_top)

    crop_h = src_h
    crop_w = int(round(src_h * target_ar))
    crop_w = min(crop_w, src_w)
    max_x = src_w - crop_w

    if mode == "center" or not observations:
        x = max_x / 2.0
        return CropPlan(crop_w, crop_h, [(0.0, int(round(x)))], static=True,
                        mode="center" if mode != "center" and not observations else mode)

    # Build a dense timeline of desired centre-x (pixels) from observations.
    duration = max(0.2, clip_end - clip_start)
    step = 0.1
    n = max(2, int(duration / step) + 1)
    timeline = [i * step for i in range(n)]

    obs_sorted = sorted(observations, key=lambda o: o.t)

    def desired_cx_at(t_abs: float) -> float:
        # nearest / interpolated observation
        if not obs_sorted:
            return 0.5 * src_w
        if t_abs <= obs_sorted[0].t:
            return obs_sorted[0].cx * src_w
        if t_abs >= obs_sorted[-1].t:
            return obs_sorted[-1].cx * src_w
        for a, b in zip(obs_sorted, obs_sorted[1:]):
            if a.t <= t_abs <= b.t:
                f = (t_abs - a.t) / max(1e-6, b.t - a.t)
                return (a.cx + f * (b.cx - a.cx)) * src_w
        return obs_sorted[-1].cx * src_w

    raw_cx = [desired_cx_at(clip_start + t) for t in timeline]

    # smart_auto: if the speaker barely moves, lock to a static crop (calmer).
    spread = (max(raw_cx) - min(raw_cx)) / max(1.0, src_w)
    if mode == "smart_auto" and spread < 0.06:
        avg = sum(raw_cx) / len(raw_cx)
        x = _clamp(avg - crop_w / 2.0, 0, max_x)
        return CropPlan(crop_w, crop_h, [(0.0, int(round(x)))], static=True, mode="smart_auto")

    # convert centre -> left edge, smooth, velocity-limit
    left = [_clamp(cx - crop_w / 2.0, 0, max_x) for cx in raw_cx]
    left = _ema_smooth(left, alpha=0.16)
    # max pan speed ~ 18% of max_x per second
    left = _limit_velocity(left, max_step=max(2.0, 0.18 * max(1.0, max_x) * step))
    left = [_clamp(v, 0, max_x) for v in left]

    # decimate to ~5 keys/sec for the sendcmd file
    keys: list[tuple[float, int]] = []
    last_x = None
    for t, x in zip(timeline, left):
        xi = int(round(x))
        if last_x is None or abs(xi - last_x) >= 1 or t == timeline[-1]:
            keys.append((round(t, 3), xi))
            last_x = xi
    if len(keys) < 2:
        keys.append((round(duration, 3), keys[-1][1]))

    log.info("crop plan mode=%s keys=%d spread=%.3f", mode, len(keys), spread)
    return CropPlan(crop_w, crop_h, keys, static=False, mode=mode)

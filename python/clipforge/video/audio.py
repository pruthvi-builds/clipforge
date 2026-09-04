"""Audio extraction and optional speech enhancement (all FFmpeg, no ML).

Consumer recordings (phone screen captures, OBS, Zoom exports) frequently carry
slightly damaged AAC. FFmpeg can hit a fatal decode error partway through such a
file. We therefore:
  * pass error-tolerant demux/decode flags
  * accept a *partial* extraction as long as it contains a useful amount of
    speech (the pipeline records the coverage so the UI can warn the user)
  * only hard-fail when essentially nothing decoded
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

from ..logging_setup import get_logger
from ..util.errors import NoSpeechError
from ..util.shell import require, run

log = get_logger("clipforge.audio")

FFMPEG_HINT = "Install FFmpeg: `brew install ffmpeg`"

# A conservative speech chain:
#  - highpass 90 Hz  : remove rumble / handling noise
#  - lowpass 12 kHz  : tame hiss
#  - afftdn          : gentle broadband denoise
#  - loudnorm        : EBU R128 to -16 LUFS (good for phones/social)
#  - dynaudnorm      : smooth remaining level swings
ENHANCE_FILTER = (
    "highpass=f=90,lowpass=f=12000,"
    "afftdn=nf=-25,"
    "loudnorm=I=-16:TP=-1.5:LRA=11,"
    "dynaudnorm=f=200:g=7:p=0.9"
)

# Flags that let FFmpeg push past corrupt packets instead of aborting.
_TOLERANT_INPUT = [
    "-err_detect", "ignore_err",
    "-fflags", "+discardcorrupt+igndts",
    "-analyzeduration", "100M", "-probesize", "100M",
]


@dataclass
class AudioResult:
    path: Path
    seconds: float          # duration actually decoded
    truncated: bool         # ffmpeg stopped early on a damaged stream
    source_seconds: float   # expected duration from the container


def wav_seconds(path: str | Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            fr = w.getframerate() or 1
            return w.getnframes() / float(fr)
    except Exception:
        return 0.0


def extract_audio(
    video_path: str | Path,
    out_wav: str | Path,
    *,
    enhance: bool = False,
    sample_rate: int = 16000,
    source_seconds: float = 0.0,
    min_seconds: float = 8.0,
) -> AudioResult:
    """Extract a mono WAV suitable for Whisper.

    Returns an :class:`AudioResult`. Raises :class:`NoSpeechError` only when the
    result is unusably short.
    """
    ffmpeg = require("ffmpeg", install_hint=FFMPEG_HINT)
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    af = ENHANCE_FILTER if enhance else "aresample=async=1:first_pts=0"
    res = run(
        [
            ffmpeg, "-hide_banner", "-y",
            *_TOLERANT_INPUT,
            "-i", str(video_path),
            "-vn", "-sn", "-dn",
            "-af", af,
            "-ac", "1",
            "-ar", str(sample_rate),
            "-c:a", "pcm_s16le",
            "-max_error_rate", "1.0",
            str(out_wav),
        ],
        check=False,
        timeout=None,
    )

    got = wav_seconds(out_wav) if out_wav.exists() else 0.0

    if got < min_seconds:
        tail = "\n".join(res.stderr.strip().splitlines()[-6:])
        raise NoSpeechError(
            "Could not extract usable audio from this video.",
            hint=(
                "The file's audio track appears to have no decodable speech. "
                + (f"FFmpeg said:\n{tail}" if tail else "")
            ),
        )

    truncated = False
    if source_seconds and got < source_seconds - 5.0:
        truncated = True
        log.warning(
            "audio decoded only %.0fs of %.0fs — the source audio stream is "
            "damaged past that point; continuing with the part that decoded",
            got, source_seconds,
        )
    if res.returncode != 0 and not truncated:
        # non-zero exit but full-length output: usually just packet warnings
        log.info("ffmpeg reported warnings during extraction (output looks complete)")

    log.info("extracted audio -> %s (%.0fs, %.1f KB, enhance=%s%s)",
             out_wav.name, got, out_wav.stat().st_size / 1024, enhance,
             ", TRUNCATED" if truncated else "")
    return AudioResult(out_wav, got, truncated, source_seconds or got)


def make_enhanced_track(video_path: str | Path, out_wav: str | Path) -> Path:
    """Full-rate (48 kHz stereo) enhanced audio used at final render time.

    Best-effort: callers treat a failure here as non-fatal and fall back to the
    original audio.
    """
    ffmpeg = require("ffmpeg", install_hint=FFMPEG_HINT)
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    res = run(
        [
            ffmpeg, "-hide_banner", "-y",
            *_TOLERANT_INPUT,
            "-i", str(video_path),
            "-vn",
            "-af", ENHANCE_FILTER,
            "-ar", "48000", "-ac", "2",
            "-c:a", "pcm_s16le",
            "-max_error_rate", "1.0",
            str(out_wav),
        ],
        check=False,
        timeout=None,
    )
    if not out_wav.exists() or wav_seconds(out_wav) < 1.0:
        raise RuntimeError("enhanced audio track could not be produced")
    if res.returncode != 0:
        log.info("enhanced-audio pass had warnings; using it anyway")
    return out_wav

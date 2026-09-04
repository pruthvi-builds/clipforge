"""Frame sampling + face detection for reframing.

Uses OpenCV's bundled Haar cascades (shipped inside the opencv wheel — no
download, works offline). We sample a handful of frames per second, detect
faces, and return per-timestamp face boxes. If OpenCV is missing or no faces are
found the caller falls back to a centre crop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..logging_setup import get_logger
from ..util.shell import require, run

log = get_logger("clipforge.frames")


@dataclass
class FaceObservation:
    t: float
    # normalised 0..1 centre + size relative to frame
    cx: float
    cy: float
    w: float
    h: float
    score: float = 1.0


def opencv_available() -> tuple[bool, str]:
    try:
        import cv2  # noqa: F401
        return True, "ok"
    except Exception as e:  # pragma: no cover - env dependent
        return False, f"opencv-python not installed ({e.__class__.__name__})"


def _cascade_dir() -> "Path | None":
    """Locate the Haar cascade XML directory.

    OpenCV 4.x wheels bundle these; the 5.0.0 wheel dropped them. If we can't
    find them, face tracking is skipped and reframing uses a centre crop.
    Point ``CLIPFORGE_HAARCASCADE_DIR`` at a folder containing
    ``haarcascade_frontalface_default.xml`` to force it.
    """
    import os

    import cv2  # type: ignore

    candidates: list[Path] = []
    env = os.environ.get("CLIPFORGE_HAARCASCADE_DIR")
    if env:
        candidates.append(Path(env).expanduser())
    data = getattr(cv2, "data", None)
    if data is not None and getattr(data, "haarcascades", None):
        candidates.append(Path(data.haarcascades))
    base = Path(cv2.__file__).resolve().parent
    candidates += [base / "data", base / "data" / "haarcascades"]
    for c in candidates:
        if (c / "haarcascade_frontalface_default.xml").exists():
            return c
    return None


def _load_cascades():
    import cv2  # type: ignore

    d = _cascade_dir()
    if d is None:
        return None, None
    try:
        frontal = cv2.CascadeClassifier(str(d / "haarcascade_frontalface_default.xml"))
        profile = cv2.CascadeClassifier(str(d / "haarcascade_profileface.xml"))
        if frontal.empty():
            return None, None
        return frontal, (None if profile.empty() else profile)
    except Exception:  # pragma: no cover - defensive
        return None, None


def sample_face_track(
    video_path: str | Path,
    start: float,
    end: float,
    *,
    fps: float = 4.0,
    frame_dir: Path | None = None,
) -> list[FaceObservation]:
    """Extract frames in [start, end] and detect the most prominent face in each.

    Returns a list ordered by time. Empty list => reframing should use centre.
    """
    ok, reason = opencv_available()
    if not ok:
        log.info("face tracking unavailable: %s", reason)
        return []

    import cv2  # type: ignore

    face_cascade, profile_cascade = _load_cascades()
    if face_cascade is None:
        log.info("face tracking unavailable: Haar cascades not found in this OpenCV build")
        return []

    ffmpeg = require("ffmpeg", install_hint="brew install ffmpeg")
    frame_dir = Path(frame_dir or Path(video_path).parent / "frames")
    frame_dir.mkdir(parents=True, exist_ok=True)

    duration = max(0.2, end - start)
    pattern = str(frame_dir / "f_%05d.jpg")
    # clean old frames
    for old in frame_dir.glob("f_*.jpg"):
        old.unlink()

    try:
        run(
            [
                ffmpeg, "-hide_banner", "-y",
                "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
                "-i", str(video_path),
                "-vf", f"fps={fps},scale=480:-2",
                "-q:v", "4",
                pattern,
            ],
            check=True,
            timeout=None,
        )
    except Exception as e:  # pragma: no cover - defensive; fall back to centre crop
        log.warning("frame extraction failed, reframing will use centre crop: %s", e)
        return []

    frames = sorted(frame_dir.glob("f_*.jpg"))
    obs: list[FaceObservation] = []
    for i, fp in enumerate(frames):
        t = start + (i + 0.5) / fps
        img = cv2.imread(str(fp))
        if img is None:
            continue
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=6,
                                              minSize=(int(w * 0.06), int(w * 0.06)))
        if len(faces) == 0 and profile_cascade is not None:
            faces = profile_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5,
                                                     minSize=(int(w * 0.06), int(w * 0.06)))
        if len(faces) == 0 and profile_cascade is not None:
            # also try mirrored for right-facing profiles
            faces = profile_cascade.detectMultiScale(cv2.flip(gray, 1), scaleFactor=1.15,
                                                     minNeighbors=5)
            faces = [(w - (x + fw), y, fw, fh) for (x, y, fw, fh) in faces]
        if len(faces) == 0:
            continue
        # pick the largest face (most prominent speaker)
        x, y, fw, fh = max(faces, key=lambda b: b[2] * b[3])
        obs.append(
            FaceObservation(
                t=round(t, 3),
                cx=(x + fw / 2) / w,
                cy=(y + fh / 2) / h,
                w=fw / w,
                h=fh / h,
                score=float(fw * fh) / float(w * h),
            )
        )

    # tidy frames
    for fp in frames:
        try:
            fp.unlink()
        except OSError:
            pass

    log.info("face track: %d/%d frames had a face", len(obs), len(frames))
    return obs

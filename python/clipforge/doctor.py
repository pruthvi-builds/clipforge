"""Environment self-check used by the CLI (`clipforge doctor`) and the API's
first-run setup screen."""

from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import dataclass, asdict

from .config import get_settings
from .ai.ollama_client import OllamaClient
from .transcription.transcribe import backend_status
from .video.frames import opencv_available


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _v(cmd: list[str]) -> str:
    try:
        import subprocess
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception:
        return ""


def run_checks() -> list[Check]:
    s = get_settings()
    checks: list[Check] = []

    # Python
    py_ok = sys.version_info >= (3, 10)
    checks.append(Check(
        "Python", py_ok, f"{platform.python_version()}",
        "" if py_ok else "ClipForge needs Python 3.10+.",
    ))

    # FFmpeg / ffprobe
    ff = shutil.which("ffmpeg")
    fp = shutil.which("ffprobe")
    checks.append(Check(
        "FFmpeg", bool(ff and fp),
        _v(["ffmpeg", "-version"]) if ff else "not found",
        "" if ff and fp else "Install FFmpeg:  brew install ffmpeg",
    ))

    # Transcription backends
    bs = backend_status(s)
    any_tx = any(b["available"] for b in bs)
    detail = "; ".join(f"{b['name']}: {'ok' if b['available'] else b['detail']}" for b in bs)
    checks.append(Check(
        "Transcription", any_tx, detail,
        "" if any_tx else
        "Install faster-whisper:  pip install -r requirements.txt   "
        "(or build whisper.cpp and set CLIPFORGE_WHISPERCPP_MODEL)",
    ))

    # Whisper model note (faster-whisper downloads on first use)
    checks.append(Check(
        "Whisper model", True,
        f"configured: {s.whisper_model} (downloads automatically on first run)",
    ))

    # Ollama
    client = OllamaClient(s.ollama_base_url)
    up = client.ping()
    if up:
        try:
            models = client.list_models()
        except Exception:
            models = []
        has = client.has_model(s.model_name)
        checks.append(Check(
            "Ollama", True,
            f"running at {s.ollama_base_url}; models: {', '.join(models) or 'none'}",
        ))
        checks.append(Check(
            "LLM model", has,
            f"{s.model_name} {'installed' if has else 'NOT installed'}",
            "" if has else f"ollama pull {s.model_name}",
        ))
    else:
        checks.append(Check(
            "Ollama", False,
            f"not reachable at {s.ollama_base_url}",
            "Install Ollama (https://ollama.com) then:  ollama serve  &&  "
            f"ollama pull {s.model_name}   —  ClipForge still works without it "
            "(heuristic scoring).",
        ))
        checks.append(Check("LLM model", False, "skipped (Ollama down)",
                            f"ollama pull {s.model_name}"))

    # OpenCV (face tracking)
    cv_ok, cv_reason = opencv_available()
    cascades = None
    if cv_ok:
        try:
            from .video.frames import _cascade_dir
            cascades = _cascade_dir()
        except Exception:
            cascades = None
    face_ok = cv_ok and cascades is not None
    if not cv_ok:
        detail, fix = cv_reason, ("pip install opencv-python-headless   "
                                  "(optional — reframing falls back to a centre crop)")
    elif cascades is None:
        detail = "OpenCV installed, but Haar cascade files are missing from this build"
        fix = ("pip install 'opencv-contrib-python' (4.x bundles cascades), or set "
               "CLIPFORGE_HAARCASCADE_DIR to a folder with "
               "haarcascade_frontalface_default.xml. Optional — reframing uses a "
               "centre crop without it.")
    else:
        detail, fix = f"ok (cascades: {cascades})", ""
    checks.append(Check("Face tracking (OpenCV)", face_ok, detail, fix))

    # Node (for the web UI only)
    node = shutil.which("node")
    checks.append(Check(
        "Node.js (web UI)", bool(node),
        _v(["node", "-v"]) if node else "not found",
        "" if node else "Install Node 18+ from https://nodejs.org  (only needed for the web UI)",
    ))

    return checks


def summary() -> dict:
    checks = run_checks()
    required = {"FFmpeg", "Transcription", "Python"}
    ready = all(c.ok for c in checks if c.name in required)
    return {
        "ready": ready,
        "apple_silicon": platform.machine() == "arm64" and platform.system() == "Darwin",
        "platform": f"{platform.system()} {platform.machine()}",
        "checks": [c.to_dict() for c in checks],
    }

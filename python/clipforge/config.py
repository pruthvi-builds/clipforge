"""Central configuration.

All settings come from environment variables (optionally loaded from a ``.env``
file at the repo root) and every one has a default, so ClipForge runs with an
empty environment. Settings are also persisted to / merged from the SQLite
``settings`` table so the web UI can change them at runtime.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

try:  # optional, only for developer convenience
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv is a soft dependency
    def load_dotenv(*_a, **_k):  # type: ignore
        return False


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    # Load repo-root .env first, then a data-dir .env override if present.
    load_dotenv(_REPO_ROOT / ".env")


def _b(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _s(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v is not None and v != "" else default


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip())
    except (ValueError, AttributeError):
        return default


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip())
    except (ValueError, AttributeError):
        return default


@dataclass
class Settings:
    # paths
    data_dir: Path = field(default_factory=lambda: Path(_s("CLIPFORGE_DATA_DIR", str(_REPO_ROOT / "data"))))
    db_path: Path = field(default_factory=lambda: Path(_s("CLIPFORGE_DB_PATH", str(_REPO_ROOT / "data" / "clipforge.db"))))

    # transcription
    whisper_backend: str = field(default_factory=lambda: _s("CLIPFORGE_WHISPER_BACKEND", "auto"))
    whisper_model: str = field(default_factory=lambda: _s("CLIPFORGE_WHISPER_MODEL", "small"))
    whisper_device: str = field(default_factory=lambda: _s("CLIPFORGE_WHISPER_DEVICE", "auto"))
    whisper_compute: str = field(default_factory=lambda: _s("CLIPFORGE_WHISPER_COMPUTE", "auto"))
    whispercpp_bin: str = field(default_factory=lambda: _s("CLIPFORGE_WHISPERCPP_BIN", "whisper-cli"))
    whispercpp_model: str = field(default_factory=lambda: _s("CLIPFORGE_WHISPERCPP_MODEL", str(_REPO_ROOT / "models" / "ggml-small.bin")))
    whisper_language: str = field(default_factory=lambda: _s("CLIPFORGE_WHISPER_LANGUAGE", "auto"))

    # local LLM
    ollama_base_url: str = field(default_factory=lambda: _s("OLLAMA_BASE_URL", "http://localhost:11434"))
    model_name: str = field(default_factory=lambda: _s("MODEL_NAME", "qwen2.5:7b"))
    llm_temperature: float = field(default_factory=lambda: _f("CLIPFORGE_LLM_TEMPERATURE", 0.2))
    llm_max_tokens: int = field(default_factory=lambda: _i("CLIPFORGE_LLM_MAX_TOKENS", 1600))
    llm_required: bool = field(default_factory=lambda: _b("CLIPFORGE_LLM_REQUIRED", False))

    # clip detection
    default_clips: int = field(default_factory=lambda: _i("CLIPFORGE_DEFAULT_CLIPS", 5))
    default_clip_length: str = field(default_factory=lambda: _s("CLIPFORGE_DEFAULT_CLIP_LENGTH", "auto"))
    min_clip_seconds: float = field(default_factory=lambda: _f("CLIPFORGE_MIN_CLIP_SECONDS", 12.0))
    max_clip_seconds: float = field(default_factory=lambda: _f("CLIPFORGE_MAX_CLIP_SECONDS", 95.0))
    boundary_padding: float = field(default_factory=lambda: _f("CLIPFORGE_BOUNDARY_PADDING", 0.35))

    # rendering
    output_width: int = field(default_factory=lambda: _i("CLIPFORGE_OUTPUT_WIDTH", 1080))
    output_height: int = field(default_factory=lambda: _i("CLIPFORGE_OUTPUT_HEIGHT", 1920))
    output_fps: int = field(default_factory=lambda: _i("CLIPFORGE_OUTPUT_FPS", 30))
    video_crf: int = field(default_factory=lambda: _i("CLIPFORGE_VIDEO_CRF", 18))
    audio_bitrate: str = field(default_factory=lambda: _s("CLIPFORGE_AUDIO_BITRATE", "192k"))
    reframe_mode: str = field(default_factory=lambda: _s("CLIPFORGE_REFRAME_MODE", "smart_auto"))
    caption_style: str = field(default_factory=lambda: _s("CLIPFORGE_CAPTION_STYLE", "bold"))
    enhance_audio: bool = field(default_factory=lambda: _b("CLIPFORGE_ENHANCE_AUDIO", True))
    use_ai_hooks: bool = field(default_factory=lambda: _b("CLIPFORGE_USE_AI_HOOKS", True))

    # worker / server
    worker_concurrency: int = field(default_factory=lambda: _i("CLIPFORGE_WORKER_CONCURRENCY", 1))
    api_host: str = field(default_factory=lambda: _s("CLIPFORGE_API_HOST", "127.0.0.1"))
    api_port: int = field(default_factory=lambda: _i("CLIPFORGE_API_PORT", 8787))
    cors_origins: str = field(default_factory=lambda: _s("CLIPFORGE_CORS_ORIGINS", "http://localhost:3000"))

    # ---- helpers -------------------------------------------------------
    def __post_init__(self) -> None:
        self.data_dir = self._resolve_path(self.data_dir)
        self.db_path = self._resolve_path(self.db_path)
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _resolve_path(p: str | Path) -> Path:
        """Resolve a path. Relative paths are anchored to the repo root, not the
        current working directory, so the API/worker/CLI all agree no matter
        where they are launched from."""
        pp = Path(p).expanduser()
        if not pp.is_absolute():
            pp = _REPO_ROOT / pp
        return pp.resolve()

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def uploads_dir(self) -> Path:
        d = self.data_dir / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def project_dir(self, project_id: str) -> Path:
        return self.projects_dir / project_id

    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["data_dir"] = str(self.data_dir)
        d["db_path"] = str(self.db_path)
        return d

    # Runtime overrides coming from the DB settings table.
    def apply_overrides(self, overrides: dict[str, Any]) -> None:
        for k, v in overrides.items():
            if hasattr(self, k) and v is not None and v != "":
                cur = getattr(self, k)
                try:
                    if isinstance(cur, bool):
                        v = str(v).strip().lower() in {"1", "true", "yes", "on"}
                    elif isinstance(cur, int):
                        v = int(v)
                    elif isinstance(cur, float):
                        v = float(v)
                    elif isinstance(cur, Path):
                        v = Path(v)
                except (ValueError, TypeError):
                    continue
                setattr(self, k, v)


_settings: Settings | None = None


def get_settings(reload: bool = False) -> Settings:
    global _settings
    if _settings is None or reload:
        _load_env()
        _settings = Settings()
    return _settings

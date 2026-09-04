#!/usr/bin/env bash
# One-time setup: Python venv + deps, and web deps.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> ClipForge setup"

# --- Python -------------------------------------------------------------
PY="${PYTHON:-python3}"
if [ ! -d .venv ]; then
  echo "==> creating virtualenv (.venv)"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "==> installing Python dependencies"
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

# --- Web --------------------------------------------------------------
if command -v npm >/dev/null 2>&1; then
  echo "==> installing web dependencies"
  npm --prefix web install
else
  echo "!! npm not found — skipping web UI deps (the CLI still works)"
fi

# --- env file -------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> wrote .env (from .env.example) — edit it if you like"
fi

echo
echo "==> checking your environment"
python clipforge.py doctor || true

cat <<'EOF'

Setup done.

Next:
  1. (optional) install a local LLM:   ollama pull qwen2.5:7b
  2. start everything:                 npm run start:local
     then open http://localhost:3000

Or use the CLI directly:
     source .venv/bin/activate
     python clipforge.py path/to/video.mp4 --clips 5
EOF

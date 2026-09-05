#!/usr/bin/env bash
# Wrapper used by the com.clipforge.api LaunchAgent. Keeps the FastAPI server
# running; launchd restarts it if it exits.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$ROOT/.venv/bin"
cd "$ROOT/python"
exec "$ROOT/.venv/bin/python" -m clipforge.server.app

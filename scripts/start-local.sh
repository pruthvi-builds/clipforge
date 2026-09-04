#!/usr/bin/env bash
# Start the API, the background worker and the Next.js dev server together.
# Ctrl-C stops all three.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  echo "!! no .venv found — run 'npm run setup' first" >&2
  exit 1
fi

pids=()
cleanup() {
  echo
  echo "==> shutting down"
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "==> starting API on http://127.0.0.1:${CLIPFORGE_API_PORT:-8787}"
( cd "$ROOT/python" && exec python -m clipforge.server.app ) &
pids+=($!)

echo "==> starting worker"
( cd "$ROOT/python" && exec python -m clipforge.server.worker ) &
pids+=($!)

WEB_PORT="${CLIPFORGE_WEB_PORT:-3000}"
port_free() { ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
if ! port_free "$WEB_PORT"; then
  for p in 3001 3002 3003 3004 3005; do
    if port_free "$p"; then WEB_PORT="$p"; break; fi
  done
fi

if [ -d web/node_modules ]; then
  echo "==> starting web UI on http://localhost:${WEB_PORT}"
  CLIPFORGE_WEB_PORT="$WEB_PORT" npm --prefix web run dev &
  pids+=($!)
else
  echo "!! web/node_modules missing — run 'npm --prefix web install' for the UI"
  echo "   (API + worker are running; you can still use the CLI)"
fi

echo
echo "ClipForge is up. Open http://localhost:${WEB_PORT}   (Ctrl-C to stop)"
wait

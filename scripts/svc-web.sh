#!/usr/bin/env bash
# Wrapper used by the com.clipforge.web LaunchAgent.
#
# Serves the built Next.js frontend on :3001. next.config.js rewrites /api/*
# to the local FastAPI (127.0.0.1:8787), so the browser only ever talks to
# one origin — no CORS, no split-origin config. Reached from the user's other
# devices over Tailscale at https://clipforge-mac.<tailnet>.ts.net.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export CLIPFORGE_WEB_PORT=3001
unset NEXT_PUBLIC_API_URL CLIPFORGE_API_URL
cd "$ROOT/web"
exec npm run start

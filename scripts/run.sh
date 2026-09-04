#!/usr/bin/env bash
# Thin wrapper that activates the venv (if present) then runs a component.
# Runs from python/ so the `clipforge` package is imported (not the root
# clipforge.py CLI shim, which would shadow it).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

case "${1:-}" in
  api)    cd "$ROOT/python" && exec python -m clipforge.server.app ;;
  worker) cd "$ROOT/python" && exec python -m clipforge.server.worker ;;
  test)   exec python -m pytest python/tests -q "${@:2}" ;;
  *)      echo "usage: run.sh {api|worker|test}"; exit 1 ;;
esac

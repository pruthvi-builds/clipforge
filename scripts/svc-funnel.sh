#!/usr/bin/env bash
# Wrapper used by the com.clipforge.funnel LaunchAgent. Publishes the local
# API on the machine's stable Tailscale Funnel URL
# (https://<host>.<tailnet>.ts.net) and stays in the foreground so launchd
# supervises it and restarts on drop.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Wait for tailscaled to be up and logged in before publishing.
for _ in $(seq 1 60); do
  if tailscale status >/dev/null 2>&1; then break; fi
  sleep 5
done

# Foreground funnel on :443 -> localhost:8787. Re-invoked by launchd if it exits.
exec tailscale funnel 8787

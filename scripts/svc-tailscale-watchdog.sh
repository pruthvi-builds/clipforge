#!/usr/bin/env bash
# Wrapper used by the com.clipforge.tailscale-watchdog LaunchAgent.
#
# The Tailscale app can end up not running (a reboot, macOS killing it, an
# update) with no ClipForge process any the wiser — the API/worker/web are
# all fine, but the public URL just goes dark. Check every couple of minutes
# and self-heal: relaunch the app and re-apply the Serve rule if needed.
set -uo pipefail
TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"

while true; do
  if ! "$TS" status >/dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') tailscale not running — relaunching"
    open -a Tailscale
    sleep 8
  fi

  # Re-apply Serve if it's missing (app restart resets it, and doing this
  # unconditionally is a harmless no-op when it's already set).
  if ! "$TS" serve status 2>&1 | grep -q "127.0.0.1:3001"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') serve config missing — re-applying"
    "$TS" serve --bg --https=443 3001 >/dev/null 2>&1
  fi

  sleep 120
done

#!/usr/bin/env bash
# Wrapper used by the com.clipforge.tailscaled LaunchAgent.
#
# Runs tailscaled in userspace-networking mode (no root / no sudo needed). The
# Funnel config is stored in the state dir, so publishing 127.0.0.1:8787 on
# https://<host>.<tailnet>.ts.net resumes automatically whenever this starts.
# launchd restarts it on crash and at login.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

STATE_DIR="$HOME/.clipforge-tailscale"
mkdir -p "$STATE_DIR"

exec tailscaled \
  --tun=userspace-networking \
  --socket="$STATE_DIR/tailscaled.sock" \
  --statedir="$STATE_DIR/state"

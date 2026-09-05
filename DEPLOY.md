# ClipForge deployment

The web UI is hosted on Vercel (free). The Python engine (API + worker +
ffmpeg + whisper) runs on this Mac and is exposed to the internet over a
stable **Tailscale Funnel** URL. Everything is supervised by `launchd`, so it
starts on login and restarts on crash — no manual `npm run` ever needed.

```
Browser ──▶ https://clipforge-kappa-cyan.vercel.app      (static Next.js, Vercel)
   │
   └──────▶ https://clipforge-mac.tailc2d6b9.ts.net ──▶ 127.0.0.1:8787  (FastAPI, this Mac)
                     (Tailscale Funnel)                     │
                                                            └─ worker polls the same SQLite DB
```

The Funnel URL is permanent — it only changes if the machine is renamed or the
tailnet changes. Vercel's `NEXT_PUBLIC_API_URL` points at it and should never
need updating again.

## Services (launchd user agents — no root, no sudo)

| Label                     | Runs                                        | Log                   |
|---------------------------|---------------------------------------------|-----------------------|
| `com.clipforge.api`       | `python -m clipforge.server.app` (:8787)     | `logs/api.log`        |
| `com.clipforge.worker`    | `python -m clipforge.server.worker`          | `logs/worker.log`     |
| `com.clipforge.tailscaled`| `tailscaled` (userspace) + persisted Funnel  | `logs/tailscaled.log` |

`tailscaled` runs in `--tun=userspace-networking` mode, so it needs no
privileges. Its state (including the Funnel publish rule) lives in
`~/.clipforge-tailscale/`, so Funnel resumes automatically on restart.

Plist sources are versioned in `scripts/launchagents/`; the live copies are in
`~/Library/LaunchAgents/`. Wrappers they call are `scripts/svc-*.sh`.

### Common commands

```bash
# status
launchctl list | grep clipforge
tailscale --socket=$HOME/.clipforge-tailscale/tailscaled.sock funnel status

# restart one service
launchctl kickstart -k gui/$(id -u)/com.clipforge.api

# stop / start a service
launchctl bootout    gui/$(id -u)/com.clipforge.api
launchctl bootstrap  gui/$(id -u) ~/Library/LaunchAgents/com.clipforge.api.plist

# tail logs
tail -f logs/api.log logs/worker.log logs/tailscaled.log
```

## Updating the app

```bash
git pull

# web changes: redeploy (or connect the Vercel Git integration for auto-deploy)
cd web && vercel --prod --yes

# engine changes:
pip install -r requirements.txt        # only if deps changed
launchctl kickstart -k gui/$(id -u)/com.clipforge.api
launchctl kickstart -k gui/$(id -u)/com.clipforge.worker
```

## One-time setup (already done — kept for reference / a fresh machine)

```bash
brew install tailscale
mkdir -p ~/.clipforge-tailscale

# start the userspace daemon (the launchd agent does this going forward)
tailscaled --tun=userspace-networking \
  --socket=$HOME/.clipforge-tailscale/tailscaled.sock \
  --statedir=$HOME/.clipforge-tailscale/state &

SOCK=$HOME/.clipforge-tailscale/tailscaled.sock
tailscale --socket=$SOCK up --hostname=clipforge-mac   # visit the printed URL, sign in
tailscale --socket=$SOCK funnel --bg 8787              # enable Funnel at the printed URL if prompted

# load the agents
for a in api worker tailscaled; do
  launchctl load ~/Library/LaunchAgents/com.clipforge.$a.plist
done
```

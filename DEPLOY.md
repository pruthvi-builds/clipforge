# ClipForge deployment

The web UI is hosted on Vercel (free). The Python engine (API + worker +
ffmpeg + whisper) runs on this Mac and is exposed to the internet over a
stable **Tailscale Funnel** URL. Everything is supervised by `launchd`, so it
starts on login and restarts on crash — no manual `npm run` needed.

```
Browser ──▶ clipforge-kappa-cyan.vercel.app        (static Next.js, Vercel)
   │
   └──────▶ https://<host>.<tailnet>.ts.net  ──▶  127.0.0.1:8787  (FastAPI, this Mac)
                     (Tailscale Funnel)               │
                                                      └─ worker polls the same SQLite DB
```

## Services (launchd user agents)

| Label                   | What it runs                       | Log                |
|-------------------------|------------------------------------|--------------------|
| `com.clipforge.api`     | `python -m clipforge.server.app`   | `logs/api.log`     |
| `com.clipforge.worker`  | `python -m clipforge.server.worker`| `logs/worker.log`  |
| `com.clipforge.funnel`  | `tailscale funnel 8787`            | `logs/funnel.log`  |

Plist sources are versioned in `scripts/launchagents/`; the live copies are in
`~/Library/LaunchAgents/`. Wrappers they call are `scripts/svc-*.sh`.

### Common commands

```bash
# status
launchctl list | grep clipforge
tailscale funnel status

# restart one service
launchctl kickstart -k gui/$(id -u)/com.clipforge.api

# stop / start a service
launchctl bootout gui/$(id -u)/com.clipforge.api
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.clipforge.api.plist

# tail logs
tail -f logs/api.log logs/worker.log logs/funnel.log
```

## First-time Tailscale setup (one time, needs your password + browser login)

```bash
sudo brew services start tailscale     # run the daemon at boot
sudo tailscale up                      # opens browser: sign in (free account)
tailscale funnel 8787                  # if it prints a link to enable Funnel/HTTPS, open it, approve, re-run
tailscale funnel status                # note the https URL it prints
```

Then load the funnel agent and point Vercel at that URL:

```bash
launchctl load ~/Library/LaunchAgents/com.clipforge.funnel.plist
cd web
vercel env rm NEXT_PUBLIC_API_URL production --yes
vercel env add NEXT_PUBLIC_API_URL production --value "https://<host>.<tailnet>.ts.net" --no-sensitive --yes
vercel --prod --yes
```

The Funnel URL is stable — it never changes again unless you rename the machine
or the tailnet, so this is the last time Vercel needs updating.

## Updating the app

```bash
git pull
# web changes deploy themselves via `vercel --prod` (or Vercel Git integration)
# engine changes:
pip install -r requirements.txt        # if deps changed
launchctl kickstart -k gui/$(id -u)/com.clipforge.api
launchctl kickstart -k gui/$(id -u)/com.clipforge.worker
```

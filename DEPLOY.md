# ClipForge deployment

Everything runs on this Mac. Both the frontend and the engine are served
locally and reached from the user's own devices over **Tailscale** — there is
no public tunnel, because every public tunnel we tried (Tailscale Funnel,
cloudflared quick tunnel) became the single recurring point of failure.

```
Your laptop / phone (on the tailnet)
        │
        ▼  https://pruthvis-macbook-air.tailc2d6b9.ts.net   (Tailscale Serve, tailnet-only)
   next start  :3001   ──rewrite /api/*──▶  FastAPI :8787
        │                                      │
   (built Next.js frontend)              worker polls same SQLite DB
```

One origin, so no CORS and no `NEXT_PUBLIC_API_URL`. Uploads still go in
4 MB chunks (resumable) but now at full Tailscale speed.

## Services (launchd user agents, no root)

| Label                      | Runs                                | Log                   |
|----------------------------|-------------------------------------|-----------------------|
| `com.clipforge.api`        | `python -m clipforge.server.app`    | `logs/api.log`        |
| `com.clipforge.worker`     | `python -m clipforge.server.worker` | `logs/worker.log`     |
| `com.clipforge.web`        | `next start` on :3001               | `logs/web.log`        |

All `KeepAlive` + `RunAtLoad`: start on login, respawn on crash. Tailscale
itself is the macOS app, not a launchd agent.

### Common commands

```bash
launchctl list | grep clipforge
/Applications/Tailscale.app/Contents/MacOS/Tailscale serve status

# restart one service
launchctl kickstart -k gui/$(id -u)/com.clipforge.web

# after a frontend code change: rebuild then restart
cd web && npm run build && launchctl kickstart -k gui/$(id -u)/com.clipforge.web

# after an engine change
launchctl kickstart -k gui/$(id -u)/com.clipforge.api
launchctl kickstart -k gui/$(id -u)/com.clipforge.worker

tail -f logs/*.log
```

## Accessing it

Install the Tailscale app on any device you want to use ClipForge from
(sign in with the same account, `pruthvi-builds`). Then open
**https://pruthvis-macbook-air.tailc2d6b9.ts.net**.

Tailscale itself is the **macOS app** (kernel-mode daemon, auto-starts at
login, survives reboots). Serve is configured on it:

```bash
/Applications/Tailscale.app/Contents/MacOS/Tailscale serve --bg --https=443 3001
/Applications/Tailscale.app/Contents/MacOS/Tailscale serve status
```

## The Vercel deployment

`clipforge-kappa-cyan.vercel.app` still exists but is no longer the way in
(it needed the public tunnel). Left in place as a static fallback; ignore it.

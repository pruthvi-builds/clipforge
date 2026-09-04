# ClipForge

**Turn long videos into short-form content.** Upload a podcast, interview, talk
or webinar; ClipForge transcribes it locally, finds the strongest standalone
moments, reframes them to 9:16, burns modern captions, writes hook/title
suggestions, and exports ready-to-post MP4s.

* 100% local — **no paid APIs** (no OpenAI / Anthropic / Gemini / AssemblyAM /
  Deepgram / ElevenLabs / cloud AI of any kind). Works offline after models are
  downloaded.
* Transcription: **faster-whisper** (CTranslate2) or **whisper.cpp**.
* Clip selection: hybrid **rule-based candidate detection + local LLM
  evaluation** (Ollama — Qwen / Llama / Mistral, your choice). Degrades
  gracefully to heuristics if no LLM is installed.
* Reframing: **OpenCV** face/speaker tracking with smoothing; centre-crop
  fallback.
* Captions: locally generated **ASS** subtitles (5 styles, word highlighting),
  plus `.srt` sidecars.
* No watermark on exports. Ever.

Primary target: **macOS (Apple Silicon)**. Runs on CPU; uses Metal/CUDA
automatically when available. Also runs on Intel Mac / Linux / WSL2.

---

## What you get

```
upload long video
  → ffprobe inspect
  → extract audio (FFmpeg)
  → transcribe locally (word-level timestamps)
  → segment transcript
  → rule-based candidate moments (questions, claims, numbers, stories, contrast…)
  → build 15/20/30/45/60s windows around each candidate
  → local LLM scores + labels + writes hooks (optional)
  → blended scoring (engagement / hook / clarity / self-contained / emotion / novelty …)
  → remove overlapping & duplicate clips
  → snap start/end to sentence + silence boundaries, add padding
  → smart 9:16 reframe (face tracking + smoothing)
  → burn captions, enhance audio
  → export 01_highest-potential.mp4, 02_story_….mp4, …
```

Success criterion the whole design serves: **drop in a 60-minute podcast, get
~5 genuinely interesting clips that make sense on their own, start and end
cleanly, are vertical, keep the speaker framed, have clean subtitles, and export
as ready-to-post MP4s.**

---

## Install

### 1. System prerequisites

| Tool | Why | Install (macOS) |
| --- | --- | --- |
| **Node.js 18+** | web UI | `brew install node` |
| **Python 3.10+** | engine, API, worker | `brew install python@3.12` |
| **FFmpeg + ffprobe** | all media work | `brew install ffmpeg` |
| **Ollama** *(optional)* | local LLM scoring/hooks | `brew install ollama` |

### 2. Project dependencies

```bash
cd clipforge
npm run setup
```

That creates `.venv`, installs `requirements.txt`, installs the web UI's
`node_modules`, copies `.env.example → .env`, and prints a `doctor` report.

Manual equivalent:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm --prefix web install
cp .env.example .env
```

### 3. Local LLM (optional, recommended)

```bash
ollama pull qwen2.5:7b        # or llama3.1:8b, mistral:7b, …
```

Set `MODEL_NAME` / `OLLAMA_BASE_URL` in `.env` (or in the Settings page) to
point at any model you have installed. If Ollama is absent, ClipForge uses
heuristic scoring and derives hooks from the transcript — it stays fully usable.

### 4. whisper.cpp instead of faster-whisper (optional)

If CTranslate2 wheels aren't available for your Python:

```bash
# build whisper.cpp, put `whisper-cli` on PATH, download a ggml model
export CLIPFORGE_WHISPER_BACKEND=whisper.cpp
export CLIPFORGE_WHISPERCPP_MODEL=/path/to/ggml-small.bin
```

---

## Run

```bash
npm run start:local     # API + worker + web UI, Ctrl-C stops all
# open http://localhost:3000
```

Or separately:

```bash
npm run api             # http://127.0.0.1:8787
npm run worker          # background jobs (run 1+; queue prevents CPU overload)
npm run web             # http://localhost:3000
```

CLI (see [`QUICKSTART.md`](./QUICKSTART.md)):

```bash
source .venv/bin/activate
python clipforge.py video.mp4 --clips 5
```

---

## Configuration

Everything has a default. Override via `.env`, environment variables, or the
**Settings** page (persisted to SQLite, applied on the next job). Key ones:

| Variable | Default | Meaning |
| --- | --- | --- |
| `CLIPFORGE_WHISPER_MODEL` | `small` | `tiny` / `base` / `small` / `medium` / `large-v3` |
| `CLIPFORGE_WHISPER_BACKEND` | `auto` | `faster-whisper` / `whisper.cpp` / `auto` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | local LLM endpoint |
| `MODEL_NAME` | `qwen2.5:7b` | any installed Ollama model |
| `CLIPFORGE_DEFAULT_CLIPS` | `5` | clips per run |
| `CLIPFORGE_DEFAULT_CLIP_LENGTH` | `auto` | or `15`/`30`/`45`/`60`/`90` |
| `CLIPFORGE_OUTPUT_WIDTH`×`HEIGHT` | `1080`×`1920` | export resolution |
| `CLIPFORGE_VIDEO_CRF` | `18` | H.264 quality (lower = better) |
| `CLIPFORGE_REFRAME_MODE` | `smart_auto` | `smart_auto`/`center`/`face`/`speaker` |
| `CLIPFORGE_CAPTION_STYLE` | `bold` | `clean`/`bold`/`karaoke`/`minimal`/`highlight` |
| `CLIPFORGE_ENHANCE_AUDIO` | `true` | loudnorm + light denoise |

Full list in [`.env.example`](./.env.example).

---

## Architecture

```
clipforge/
├── clipforge.py                  # CLI entrypoint  (python clipforge.py …)
├── python/clipforge/
│   ├── config.py                 # env + DB-backed settings
│   ├── db.py                     # SQLite: projects, videos, transcripts, clips, jobs, settings
│   ├── models.py                 # dataclasses (Transcript, Segment, Word, Candidate, Clip, …)
│   ├── pipeline.py               # STAGE A–H orchestrator (analyze / render / run)
│   ├── doctor.py                 # environment self-check
│   ├── util/                     # safe subprocess, filename sanitising, sentence splitter
│   ├── video/                    # probe · audio (extract + enhance) · frames (face detect)
│   │                             #   · reframe (crop plan + smoothing) · render (final FFmpeg)
│   ├── transcription/            # faster-whisper + whisper.cpp backends, on-disk cache
│   ├── clipdetect/               # segment · candidates (rule-based) · overlap · boundaries
│   ├── scoring/                  # heuristics (transparent 0-100 sub-scores) · combine (LLM blend)
│   ├── ai/                       # ollama_client · prompts · llm_analyze · hooks · JSON repair/validate
│   ├── captions/                 # ass.py (5 styles, word highlight) · srt.py
│   ├── export/                   # naming (01_highest-potential.mp4 …) · exporter (cache-aware)
│   └── server/                   # app.py (FastAPI) · jobs.py (job runner) · worker.py (loop)
├── python/tests/                 # 56 tests incl. an ffmpeg end-to-end render test
├── web/                          # Next.js 14 + TypeScript + Tailwind (dark SaaS-style UI)
│   └── src/app/                  #   /  · /create · /projects/[id] · /settings · /setup
├── scripts/                      # setup.sh · run.sh · start-local.sh
├── data/projects/<id>/           # original.* · audio.wav · transcript.json · analysis.json
│                                 #   · renders/ · thumbnails/ · frames/
├── requirements.txt · pyproject.toml · .env.example
```

### The clip algorithm (why it's hybrid)

Asking an LLM to pick timestamps out of a 2-hour transcript is unreliable and
slow. Instead:

* **A. Segment** the transcript into timed sentences + pause-separated blocks.
* **B. Rule-based seeds** — score every sentence for questions, strong claims,
  numbers, contrast, emotion, first-person story, actionable advice; drop
  filler and low-confidence ASR.
* **C. Candidate windows** — grow ~15/20/30/45/60 s windows around each seed,
  backwards first (setup/context) then forwards (payoff), snapped to sentences.
* **D. Local LLM** evaluates the *short list* (6 at a time), returns strict JSON
  (`score`, `hook`, `alt_hook`, `category`, `reason`, `self_contained`,
  `emphasis_words`). Malformed JSON is repaired, re-tried, then validated;
  failure → keep heuristics.
* **E. Blended score** — transparent heuristic sub-scores; LLM only moves
  `overall` / `engagement`. No fake precision, no virality claims — it's
  **short-form potential** (structure, hook, clarity, standalone value).
* **F. De-dup** — greedy by score; drop clips overlapping >45 % or textually
  near-identical.
* **G. Boundary refinement** — snap to the nearest sentence, then to an
  inter-word silence so nothing is cut mid-word; add 0.2–1.0 s padding.
* **H. Export top N.**

### Reframing

Sample ~4 fps of frames in the clip window, detect the most prominent face
(OpenCV Haar frontal + profile, offline). Convert face centres to a portrait
crop-window path, smooth with a two-pass EMA and a velocity limit so the crop
glides. If the speaker barely moves, lock to a static crop. No face / no
OpenCV → centre crop. FFmpeg applies the moving crop via a generated `sendcmd`
script.

### Jobs

Long work never blocks an HTTP request. `POST /api/projects/:id/analyze`
enqueues a row in the `jobs` table; the worker claims one at a time
(`queued → processing → completed/failed`) and streams `{stage, progress,
message}` back. The frontend polls `GET /api/jobs/:id`. Stale `processing` jobs
are re-queued on worker start.

### Caching / reuse

Transcript, video metadata, face frames and renders are all cached by content
fingerprint. Changing a caption style re-renders only; changing crop mode never
re-runs the LLM; re-analysing never re-transcribes unchanged audio.

---

## API

Local only (binds `127.0.0.1`). The web app proxies `/api/*` to it.

| Method & path | Purpose |
| --- | --- |
| `GET /api/health` · `GET /api/setup` | version · environment check |
| `GET/PUT /api/settings` | runtime settings |
| `GET /api/ollama/models` | installed local models |
| `POST /api/projects` | create project |
| `POST /api/projects/:id/upload` | upload video (multipart) → probe |
| `POST /api/projects/:id/analyze` | enqueue analyze (+render) job |
| `POST /api/projects/:id/render` | enqueue render-all job |
| `GET /api/projects` · `GET /api/projects/:id` | list · detail |
| `GET /api/projects/:id/transcript` | full transcript JSON |
| `GET /api/projects/:id/clips` | clip cards |
| `DELETE /api/projects/:id` | delete project + files |
| `POST /api/clips/:id/render` | re-render one clip (with editor overrides) |
| `GET /api/jobs/:id` · `GET /api/projects/:id/jobs` | job status |
| `GET /api/clips/:id/download` · `GET /api/media/:id/...` | files |

---

## Testing

```bash
npm test                          # all 56 tests
.venv/bin/python -m pytest python/tests -m e2e     # only the ffmpeg render test
```

Covered: sentence splitting, candidate seeding & windowing, overlap de-dup,
boundary snapping, LLM-JSON repair/validation, ASS/SRT generation (all 5
styles), heuristic scoring, filename rules & path-traversal sanitising, SQLite
CRUD + job lifecycle, the full analyze pipeline (transcription/LLM stubbed), and
an **end-to-end** test that builds a real video with FFmpeg and verifies the
export is a genuine 1080×1920 H.264 MP4 with the right duration and sidecars.

---

## Security notes (local app, still hardened)

* Uploaded filenames are sanitised (`sanitize_filename`) — no path traversal,
  no shell metacharacters, never starts with `.`/`-`.
* All media commands use `subprocess` with argument **lists** (never a shell
  string); binaries resolved via `which` with clear "install X" errors.
* File serving is confined to the project directory via `safe_join`.
* Only supported extensions are accepted; every upload is validated with
  `ffprobe` before processing.

---

## License

MIT. Exports carry no watermark and no attribution requirement.

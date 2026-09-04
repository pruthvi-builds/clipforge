# ClipForge — Quick Start

Exact commands to go from nothing to ready-to-post shorts. Everything runs
locally; no paid APIs, no account, works offline after the first model download.

## 0. Prerequisites (install once)

```bash
# macOS (Homebrew). Linux: use your package manager. Windows: use WSL2.
brew install node python@3.12 ffmpeg
# optional but recommended — the local LLM that scores/labels clips
brew install ollama
```

## 1. Get the code + install

```bash
git clone <your-fork-or-copy> clipforge
cd clipforge

npm run setup          # creates .venv, installs Python + web deps, writes .env
```

`npm run setup` runs `python clipforge.py doctor` at the end so you can see
exactly what is and isn't ready.

## 2. (Optional) pull a local LLM

```bash
ollama pull qwen2.5:7b          # or: llama3.1:8b  /  mistral:7b
```

ClipForge works **without** this — it falls back to heuristic scoring — but the
local LLM gives better clip selection, hooks and word highlighting.

## 3. Start everything

```bash
npm run start:local
```

Launches the API (`:8787`), the background worker, and the web UI.
Open **http://localhost:3000**, drop in a video, pick options, click
**Create shorts**.

Run the pieces separately (e.g. more than one worker):

```bash
npm run api        # FastAPI backend
npm run worker     # background job worker  (run as many as you like)
npm run web        # Next.js dev server
```

## 4. Or use the CLI (no web UI needed)

```bash
source .venv/bin/activate

python clipforge.py doctor
python clipforge.py path/to/podcast.mp4 --clips 5
python clipforge.py path/to/talk.mov --clips 3 --length 30 \
    --style podcast --caption-style karaoke --reframe face --out ./my-shorts

python clipforge.py analyze video.mp4 --clips 8      # select only, no render
python clipforge.py render <project-id> --only 1,3   # render specific clips
```

Finished clips land in `data/projects/<id>/renders/` as
`01_highest-potential.mp4`, `02_story_….mp4`, … each with matching `.srt` /
`.ass` / `.jpg` sidecars. No watermark.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `FFmpeg was not found` | `brew install ffmpeg`, then restart |
| `Could not extract usable audio` / "partial — damaged source" | Some phone/screen recordings have a slightly corrupt AAC track. ClipForge now decodes as much as it can and warns you on the project page; clip search covers the part that decoded. To recover the whole thing, remux first: `ffmpeg -err_detect ignore_err -i in.mov -c:v copy -c:a pcm_s16le fixed.mov` and upload `fixed.mov`. |
| `faster-whisper is not installed` | `source .venv/bin/activate && pip install -r requirements.txt` |
| Clips have generic labels / no AI hooks | Ollama isn't running or model not pulled — `ollama serve` + `ollama pull qwen2.5:7b` |
| Reframe always centre-crops | OpenCV 5.0.0 wheels omit Haar cascades — `pip install "opencv-python-headless<5"` or set `CLIPFORGE_HAARCASCADE_DIR`. Face tracking is optional; centre crop still works. |
| Web UI can't reach API | make sure `npm run api` is running on `:8787` |
| `objc[…] Class AVFFrameReceiver is implemented in both …` | Harmless stderr noise — PyAV and OpenCV each vendor libavdevice. ClipForge shells out to the `ffmpeg` binary, so it has no effect. |

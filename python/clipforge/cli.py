"""ClipForge command-line interface.

Examples
--------
    python clipforge.py doctor
    python clipforge.py input.mp4 --clips 5
    python clipforge.py input.mp4 --clips 3 --length 30 --style podcast \\
        --caption-style karaoke --reframe face --out ./my-shorts
    python clipforge.py analyze input.mp4            # transcribe + select only
    python clipforge.py render <project-id>          # render a prior analysis
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from . import __version__
from .config import get_settings
from .logging_setup import setup_logging, get_logger
from .util.errors import ClipForgeError
from .util.fsutil import new_project_id, sanitize_filename, ensure_project_tree

log = get_logger("clipforge.cli")


# --------------------------------------------------------------------------
def _progress_printer():
    last = {"line": ""}
    start = time.time()

    def cb(frac: float, stage: str, msg: str) -> None:
        bar_len = 26
        filled = int(bar_len * max(0.0, min(1.0, frac)))
        bar = "█" * filled + "░" * (bar_len - filled)
        line = f"\r[{bar}] {frac*100:5.1f}%  {stage:<13} {msg[:44]:<44}"
        sys.stdout.write(line)
        sys.stdout.flush()
        last["line"] = line

    def done():
        sys.stdout.write("\r" + " " * (len(last["line"]) + 4) + "\r")
        sys.stdout.flush()
        print(f"done in {time.time()-start:.1f}s")

    cb.done = done  # type: ignore
    return cb


def _import_pipeline():
    from . import pipeline
    return pipeline


# --------------------------------------------------------------------------
def cmd_doctor(_args) -> int:
    from .doctor import run_checks, summary
    s = summary()
    print(f"ClipForge {__version__}  —  {s['platform']}"
          f"{'  (Apple Silicon)' if s['apple_silicon'] else ''}\n")
    for c in s["checks"]:
        mark = "✓" if c["ok"] else "⚠"
        print(f"  {mark}  {c['name']:<24} {c['detail']}")
        if not c["ok"] and c["fix"]:
            print(f"       ↳ {c['fix']}")
    print()
    print("READY — core requirements satisfied." if s["ready"]
          else "NOT READY — install the items marked ⚠ above (FFmpeg + a transcription backend are required).")
    return 0 if s["ready"] else 1


def _prepare_project(input_path: Path, style: str) -> tuple[str, Path, Path]:
    s = get_settings()
    pid = new_project_id()
    pdir = s.project_dir(pid)
    tree = ensure_project_tree(pdir)
    dst = pdir / ("original" + input_path.suffix.lower())
    shutil.copy2(input_path, dst)
    return pid, pdir, dst


def cmd_run(args) -> int:
    from .db import init_db, create_project, set_project_status, upsert_video, replace_clips
    pipeline = _import_pipeline()
    s = get_settings()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise ClipForgeError(f"Input file not found: {input_path}")

    init_db()
    pid, pdir, src = _prepare_project(input_path, args.style)
    create_project(pid, sanitize_filename(input_path.name), args.style)
    set_project_status(pid, "processing")
    print(f"project {pid}  →  {pdir}")

    aopts = pipeline.AnalyzeOptions(
        n_clips=args.clips,
        clip_length=args.length,
        style=args.style,
        use_llm=not args.no_llm,
        topic_hint=args.topic or "",
    )
    ropts = pipeline.RenderOptions(
        reframe_mode=args.reframe,
        caption_style=args.caption_style,
        use_captions=not args.no_captions,
        enhance_audio=not args.no_enhance,
        use_ai_hooks=not args.no_llm,
    )

    cb = _progress_printer()
    try:
        if args.analyze_only:
            analysis = pipeline.analyze(pdir, src, aopts, settings=s, on_progress=cb)
            renders = []
        else:
            analysis = pipeline.run(pdir, src, aopts, ropts, settings=s, on_progress=cb)
            renders = analysis.get("renders", [])
        cb.done()  # type: ignore
    except ClipForgeError as e:
        cb.done()  # type: ignore
        set_project_status(pid, "failed", e.message)
        print(f"\nERROR: {e.message}")
        if e.hint:
            print(f"HINT:  {e.hint}")
        return 2

    upsert_video(pid, analysis["meta"], sanitize_filename(input_path.name))
    replace_clips(pid, analysis["clips"])
    set_project_status(pid, "completed")

    print(f"\n{len(analysis['clips'])} clips selected"
          f"  (LLM: {'yes' if analysis.get('llm_used') else 'heuristics only'})\n")
    for c in analysis["clips"]:
        print(f"  #{c['index']}  score {c['score']['overall']:>3}  "
              f"{c['duration']:>4.0f}s  [{c['category']}]  {c['hook']}")
    if renders:
        out_dir = pdir / "renders"
        if args.out:
            out_dir = _copy_renders(renders, Path(args.out).expanduser())
        print(f"\nrenders → {out_dir}")
        for r in renders:
            if r["status"] == "completed":
                print(f"  #{r['index']}  {Path(r['mp4']).name}")
            else:
                print(f"  #{r['index']}  FAILED: {r.get('error')}")
    else:
        print(f"\nanalysis written → {pdir/'analysis.json'}")
        print(f"render later with:  python clipforge.py render {pid}")
    return 0


def _copy_renders(renders, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in renders:
        if r["status"] != "completed":
            continue
        for key in ("mp4", "srt", "ass", "thumbnail"):
            p = r.get(key)
            if p and Path(p).exists():
                shutil.copy2(p, out_dir / Path(p).name)
    return out_dir


def cmd_analyze(args) -> int:
    args.analyze_only = True
    args.out = None
    return cmd_run(args)


def cmd_render(args) -> int:
    from .db import get_project, replace_clips, set_project_status
    pipeline = _import_pipeline()
    s = get_settings()
    pdir = s.project_dir(args.project_id)
    if not (pdir / "analysis.json").exists():
        raise ClipForgeError(f"No analysis for project {args.project_id}. Run analyze first.")
    ropts = pipeline.RenderOptions(
        reframe_mode=args.reframe,
        caption_style=args.caption_style,
        use_captions=not args.no_captions,
        enhance_audio=not args.no_enhance,
        only_indexes=[int(x) for x in args.only.split(",")] if args.only else [],
    )
    cb = _progress_printer()
    renders = pipeline.render(pdir, ropts, settings=s, on_progress=cb, force=args.force)
    cb.done()  # type: ignore
    out_dir = pdir / "renders"
    if args.out:
        out_dir = _copy_renders(renders, Path(args.out).expanduser())
    print(f"\nrenders → {out_dir}")
    for r in renders:
        tag = Path(r["mp4"]).name if r["status"] == "completed" else f"FAILED: {r.get('error')}"
        print(f"  #{r['index']}  {tag}")
    return 0


# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clipforge",
        description="Turn long videos into short-form clips — fully local, no paid APIs.",
    )
    p.add_argument("--version", action="version", version=f"ClipForge {__version__}")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command")

    def add_common(sp):
        sp.add_argument("--clips", type=int, default=5, help="number of clips (default 5)")
        sp.add_argument("--length", default="auto",
                        choices=["auto", "15", "30", "45", "60", "90"])
        sp.add_argument("--style", default="general",
                        choices=["general", "educational", "podcast", "story", "interview"])
        sp.add_argument("--reframe", default="smart_auto",
                        choices=["smart_auto", "center", "face", "speaker"])
        sp.add_argument("--caption-style", dest="caption_style", default="bold",
                        choices=["clean", "bold", "karaoke", "minimal", "highlight"])
        sp.add_argument("--topic", default="", help="optional topic hint for the LLM")
        sp.add_argument("--no-llm", action="store_true", help="skip local LLM, heuristics only")
        sp.add_argument("--no-captions", action="store_true")
        sp.add_argument("--no-enhance", action="store_true", help="don't clean up audio")
        sp.add_argument("--out", default=None, help="copy finished clips here")
        sp.add_argument("--force", action="store_true", help="ignore caches")

    sp_doctor = sub.add_parser("doctor", help="check your environment")
    sp_doctor.set_defaults(func=cmd_doctor)

    sp_run = sub.add_parser("run", help="analyze + render a video end-to-end")
    sp_run.add_argument("input")
    add_common(sp_run)
    sp_run.add_argument("--analyze-only", action="store_true")
    sp_run.set_defaults(func=cmd_run)

    sp_an = sub.add_parser("analyze", help="transcribe + select clips (no render)")
    sp_an.add_argument("input")
    add_common(sp_an)
    sp_an.set_defaults(func=cmd_analyze)

    sp_re = sub.add_parser("render", help="render clips from a prior analysis")
    sp_re.add_argument("project_id")
    sp_re.add_argument("--reframe", default="smart_auto",
                       choices=["smart_auto", "center", "face", "speaker"])
    sp_re.add_argument("--caption-style", dest="caption_style", default="bold",
                       choices=["clean", "bold", "karaoke", "minimal", "highlight"])
    sp_re.add_argument("--only", default="", help="comma-separated clip indexes")
    sp_re.add_argument("--no-captions", action="store_true")
    sp_re.add_argument("--no-enhance", action="store_true")
    sp_re.add_argument("--out", default=None)
    sp_re.add_argument("--force", action="store_true")
    sp_re.set_defaults(func=cmd_render)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # bare-file shorthand: `clipforge input.mp4 --clips 5`
    if argv and not argv[0].startswith("-") and argv[0] not in {
        "doctor", "run", "analyze", "render",
    } and Path(argv[0]).suffix.lower() in {
        ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
    }:
        argv = ["run", *argv]

    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging("DEBUG" if getattr(args, "verbose", False) else "INFO")

    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return int(args.func(args) or 0)
    except ClipForgeError as e:
        print(f"\nERROR: {e.message}")
        if e.hint:
            print(f"HINT:  {e.hint}")
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

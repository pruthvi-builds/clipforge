"""The end-to-end pipeline orchestrator.

``analyze`` runs stages A-G and writes ``analysis.json``.
``render`` renders the chosen clips.
``run`` does both. Every stage reports real progress through ``on_progress``.

Each stage is independently cached so changing a caption style never re-runs
transcription and changing crop mode never re-runs the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import Settings, get_settings
from .logging_setup import get_logger
from .models import Candidate, Clip, ClipScore, Transcript, VideoMeta
from .util.errors import ClipForgeError
from .util.fsutil import ensure_project_tree, read_json, write_json
from .video.probe import probe_video
from .video.audio import extract_audio, make_enhanced_track
from .transcription.transcribe import transcribe_cached
from .clipdetect.segment import build_timed_sentences
from .clipdetect.candidates import find_seeds, generate_candidates
from .clipdetect.overlap import deduplicate
from .clipdetect.boundaries import refine_boundaries
from .scoring.heuristics import heuristic_score
from .scoring.combine import blend, length_penalty
from .ai.llm_analyze import LLMAnalyzer
from .ai.hooks import generate_hook
from .export.exporter import export_clip, ExportResult
from .export.naming import clip_slug

log = get_logger("clipforge.pipeline")

# progress(fraction 0..1, stage_key, human message)
ProgressFn = Callable[[float, str, str], None]


@dataclass
class AnalyzeOptions:
    n_clips: int = 5
    clip_length: str = "auto"          # auto | 15 | 30 | 45 | 60 | 90
    style: str = "general"             # general|educational|podcast|story|interview
    use_llm: bool = True
    topic_hint: str = ""


@dataclass
class RenderOptions:
    reframe_mode: str = "fit"
    caption_style: str = "bold"
    use_captions: bool = True
    enhance_audio: bool = True
    use_ai_hooks: bool = True
    only_indexes: list[int] = field(default_factory=list)


def _noop(_f: float, _s: str, _m: str) -> None:  # pragma: no cover
    pass


def _stage(on_progress: ProgressFn, lo: float, hi: float):
    def report(frac: float, msg: str, key: str) -> None:
        on_progress(lo + (hi - lo) * max(0.0, min(1.0, frac)), key, msg)
    return report


# --------------------------------------------------------------------------
# ANALYZE
# --------------------------------------------------------------------------
def analyze(
    project_dir: str | Path,
    src_video: str | Path,
    opts: AnalyzeOptions,
    *,
    settings: Settings | None = None,
    on_progress: ProgressFn = _noop,
    force: bool = False,
) -> dict:
    settings = settings or get_settings()
    project_dir = Path(project_dir)
    tree = ensure_project_tree(project_dir)
    src_video = Path(src_video)

    if opts.clip_length and opts.clip_length != "auto":
        settings.default_clip_length = str(opts.clip_length)

    # ---- stage: probe -------------------------------------------------
    on_progress(0.01, "prepare", "Inspecting video")
    meta = probe_video(src_video)
    write_json(project_dir / "meta.json", meta.to_dict())
    on_progress(0.05, "prepare", "Video loaded")

    if not meta.has_audio:
        raise ClipForgeError(
            "This video has no audio track, so there is nothing to transcribe.",
            hint="ClipForge needs spoken audio to find short-form moments.",
        )

    # ---- stage: audio ----------------------------------------------
    audio_wav = project_dir / "audio.wav"
    st = _stage(on_progress, 0.05, 0.12)
    st(0.1, "Extracting audio", "audio")
    audio_res = extract_audio(
        src_video, audio_wav, enhance=False, sample_rate=16000,
        source_seconds=meta.duration,
    )
    warnings: list[str] = []
    if audio_res.truncated:
        warnings.append(
            f"Only the first {audio_res.seconds / 60:.0f} min of audio could be "
            f"decoded — this file's audio track is damaged after that point, so "
            f"clip search is limited to that range."
        )
        st(1.0, "Audio extracted (partial — damaged source)", "audio")
    else:
        st(1.0, "Audio extracted", "audio")

    # ---- stage: transcription -------------------------------------
    transcript_path = project_dir / "transcript.json"
    st = _stage(on_progress, 0.12, 0.55)
    transcript = transcribe_cached(
        audio_wav, transcript_path,
        settings=settings,
        progress=lambda f, m: st(f, m, "transcription"),
        force=force,
    )
    log.info("transcript: %d segments, lang=%s, word_ts=%s",
             len(transcript.segments), transcript.language, transcript.has_word_timestamps)

    # ---- stage: segmentation + candidates ------------------------
    st = _stage(on_progress, 0.55, 0.62)
    st(0.2, "Segmenting transcript", "candidates")
    sentences = build_timed_sentences(transcript)
    seeds = find_seeds(sentences)
    candidates = generate_candidates(sentences, seeds, settings)
    if not candidates:
        # last resort: window the whole thing into complete-thought chunks
        candidates = _fallback_windows(sentences, settings)
    st(1.0, f"{len(candidates)} candidate moments", "candidates")

    # ---- stage: heuristic scoring -------------------------------
    for c in candidates:
        c.score = heuristic_score(c)

    # ---- stage: local LLM evaluation --------------------------
    st = _stage(on_progress, 0.62, 0.82)
    llm_used_any = False
    if opts.use_llm:
        analyzer = LLMAnalyzer(settings)
        ok, reason = analyzer.available()
        if ok:
            st(0.02, "Scoring moments with local AI", "llm")
            analyzer.evaluate(
                candidates,
                topic_hint=opts.topic_hint or transcript.text[:220],
                progress=lambda f, m: st(f, m, "llm"),
            )
            llm_used_any = any(c.llm_used for c in candidates)
        else:
            log.info("LLM unavailable, heuristics only: %s", reason)
            on_progress(0.82, "llm", f"Local AI not used ({reason.split('.')[0]})")
    else:
        on_progress(0.82, "llm", "Local AI disabled — using heuristics")

    # blend LLM overall into scores
    for c in candidates:
        llm_overall = getattr(c, "_llm_overall", None)
        c.score = blend(c.score, llm_overall, llm_weight=0.5 if c.llm_used else 0.0)
        c.score.overall = length_penalty(c.score.overall, c.duration)

    # ---- stage: dedupe + select --------------------------------
    st = _stage(on_progress, 0.82, 0.9)
    st(0.3, "Removing overlapping clips", "select")
    unique = deduplicate(candidates)
    # short sources can collapse to very few unique windows — relax progressively
    if len(unique) < opts.n_clips:
        for mo, ts in ((0.55, 0.7), (0.65, 0.78), (0.75, 0.85)):
            relaxed = deduplicate(candidates, max_overlap=mo, max_text_sim=ts)
            if len(relaxed) > len(unique):
                unique = relaxed
            if len(unique) >= opts.n_clips:
                break
    unique.sort(key=lambda c: c.score.overall, reverse=True)
    chosen = unique[: max(1, opts.n_clips)]
    chosen.sort(key=lambda c: c.start)

    # ---- stage: boundary refinement + hooks -------------------
    clips: list[Clip] = []
    for i, cand in enumerate(chosen, start=1):
        start, end, seg_out, clean_sents = refine_boundaries(
            cand, sentences, settings, video_duration=meta.duration
        )
        clip = Clip(
            index=i,
            start=start,
            end=end,
            text=" ".join(clean_sents).strip() or cand.text,
            score=cand.score,
            hook=cand.hook,
            alt_hook=cand.alt_hook,
            opening_text=cand.opening_text,
            category=cand.category,
            reason=cand.reason or f"Seeded by: {cand.seed_reason}",
            self_contained=cand.self_contained,
            segments=seg_out,
            emphasis_words=cand.emphasis_words,
            llm_used=cand.llm_used,
        )
        clip = generate_hook(clip, settings, use_ai=opts.use_llm and settings.use_ai_hooks)
        clip.slug = clip_slug(clip.hook or clip.category)
        clips.append(clip)
        st((i / max(1, len(chosen))), "Refining clip boundaries", "select")

    # re-rank final clips by score for display index, keep chronological order too
    ranked = sorted(clips, key=lambda c: c.score.overall, reverse=True)
    for rank, c in enumerate(ranked, start=1):
        c.index = rank
    clips = sorted(clips, key=lambda c: c.index)

    if transcript.duration and meta.duration and transcript.duration < meta.duration * 0.6 \
            and not audio_res.truncated:
        warnings.append(
            "Speech was only detected in part of this video — the rest may be "
            "music, silence or noise."
        )

    analysis = {
        "meta": meta.to_dict(),
        "language": transcript.language,
        "transcript_backend": transcript.backend,
        "transcript_model": transcript.model,
        "has_word_timestamps": transcript.has_word_timestamps,
        "llm_used": llm_used_any,
        "n_candidates": len(candidates),
        "n_unique": len(unique),
        "audio_seconds": round(audio_res.seconds, 1),
        "warnings": warnings,
        "options": opts.__dict__,
        "clips": [c.to_dict() for c in clips],
    }
    write_json(project_dir / "analysis.json", analysis)
    on_progress(0.92, "select", f"Selected {len(clips)} clips")
    return analysis


def _fallback_windows(sentences, settings) -> list[Candidate]:
    """No rule-based seeds fired — build complete-thought windows anyway."""
    out: list[Candidate] = []
    i = 0
    n = len(sentences)
    target = 35.0
    while i < n:
        lo = i
        while i + 1 < n and sentences[i].end - sentences[lo].start < target:
            i += 1
        s, e = sentences[lo].start, sentences[i].end
        if e - s >= settings.min_clip_seconds:
            out.append(Candidate(
                start=s, end=e,
                text=" ".join(sentences[k].text for k in range(lo, i + 1)),
                seed_reason="even split",
            ))
        i += 1
    return out


# --------------------------------------------------------------------------
# RENDER
# --------------------------------------------------------------------------
def render(
    project_dir: str | Path,
    ropts: RenderOptions,
    *,
    settings: Settings | None = None,
    on_progress: ProgressFn = _noop,
    force: bool = False,
) -> list[dict]:
    settings = settings or get_settings()
    project_dir = Path(project_dir)
    analysis = read_json(project_dir / "analysis.json")
    if not analysis:
        raise ClipForgeError("No analysis found. Run analysis first.")

    meta = VideoMeta(**analysis["meta"])
    src_video = Path(meta.path)
    if not src_video.exists():
        # project may have been moved; look for original.* in project dir
        for cand in project_dir.glob("original.*"):
            src_video = cand
            break
    tree = ensure_project_tree(project_dir)
    renders_dir = tree["renders"]

    # optional pre-rendered enhanced audio (shared across clips)
    enhanced_audio = None
    if ropts.enhance_audio:
        enhanced_audio = project_dir / "audio_enhanced.wav"
        if not enhanced_audio.exists() or force:
            on_progress(0.02, "render", "Enhancing audio")
            try:
                make_enhanced_track(src_video, enhanced_audio)
            except Exception as e:  # non-fatal
                log.warning("audio enhance failed, using original: %s", e)
                enhanced_audio = None

    clip_dicts = analysis["clips"]
    if ropts.only_indexes:
        clip_dicts = [c for c in clip_dicts if c["index"] in ropts.only_indexes]

    results: list[dict] = []
    total = max(1, len(clip_dicts))
    for n, cd in enumerate(clip_dicts):
        clip = _clip_from_dict(cd)
        top = (clip.index == 1)
        lo = 0.05 + 0.9 * (n / total)
        hi = 0.05 + 0.9 * ((n + 1) / total)
        st = _stage(on_progress, lo, hi)
        try:
            res: ExportResult = export_clip(
                clip,
                src_video=src_video,
                meta=meta,
                out_dir=renders_dir,
                settings=settings,
                reframe_mode=ropts.reframe_mode,
                caption_style=ropts.caption_style,
                use_captions=ropts.use_captions,
                enhance_audio=ropts.enhance_audio,
                enhanced_audio_path=enhanced_audio,
                highlight_words=clip.emphasis_words,
                frames_dir=tree["frames"],
                progress=lambda f, m: st(f, m, "render"),
                force=force,
                top=top,
            )
            results.append({
                "index": clip.index,
                "mp4": str(res.mp4),
                "srt": str(res.srt) if res.srt else None,
                "ass": str(res.ass) if res.ass else None,
                "thumbnail": str(res.thumbnail) if res.thumbnail else None,
                "duration": res.duration,
                "cached": res.cached,
                "status": "completed",
            })
        except ClipForgeError as e:
            log.error("clip %d render failed: %s", clip.index, e.message)
            results.append({"index": clip.index, "status": "failed", "error": e.message})

    write_json(project_dir / "renders.json", {"results": results})
    on_progress(1.0, "render", f"Rendered {sum(1 for r in results if r['status']=='completed')} clips")
    return results


def _clip_from_dict(cd: dict) -> Clip:
    from .models import Segment
    return Clip(
        index=cd["index"],
        start=cd["start"],
        end=cd["end"],
        text=cd["text"],
        score=ClipScore(**cd["score"]),
        hook=cd.get("hook", ""),
        alt_hook=cd.get("alt_hook", ""),
        opening_text=cd.get("opening_text", ""),
        category=cd.get("category", "insight"),
        reason=cd.get("reason", ""),
        self_contained=bool(cd.get("self_contained", True)),
        slug=cd.get("slug", ""),
        segments=[Segment.from_dict(s) for s in cd.get("segments", [])],
        emphasis_words=cd.get("emphasis_words", []),
        llm_used=bool(cd.get("llm_used", False)),
    )


# --------------------------------------------------------------------------
# RUN (analyze + render)
# --------------------------------------------------------------------------
def run(
    project_dir: str | Path,
    src_video: str | Path,
    aopts: AnalyzeOptions,
    ropts: RenderOptions,
    *,
    settings: Settings | None = None,
    on_progress: ProgressFn = _noop,
    force: bool = False,
) -> dict:
    def analyze_progress(frac, key, msg):
        on_progress(0.0 + 0.55 * frac, key, msg)

    def render_progress(frac, key, msg):
        on_progress(0.55 + 0.45 * frac, key, msg)

    analysis = analyze(project_dir, src_video, aopts, settings=settings,
                       on_progress=analyze_progress, force=force)
    renders = render(project_dir, ropts, settings=settings,
                     on_progress=render_progress, force=force)
    analysis["renders"] = renders
    return analysis

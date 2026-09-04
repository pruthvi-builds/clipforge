"use client";

import { useState } from "react";
import type { Clip } from "@/lib/types";
import { fmtDuration, scoreColor } from "@/lib/format";
import { apiUrl } from "@/lib/api";

const SUBSCORES: [keyof Clip["score"], string][] = [
  ["engagement", "Engagement"],
  ["hook", "Hook"],
  ["clarity", "Clarity"],
  ["self_contained", "Self-contained"],
  ["emotion", "Emotion"],
  ["novelty", "Novelty"],
];

export function ClipCard({
  clip,
  rank,
  onEdit,
  onRegenerate,
  busy,
}: {
  clip: Clip;
  rank: number;
  onEdit: () => void;
  onRegenerate: () => void;
  busy?: boolean;
}) {
  const [showText, setShowText] = useState(false);
  const rendered = clip.render_status === "completed" && clip.render_url;

  return (
    <div className="card overflow-hidden">
      <div className="flex gap-4 p-4">
        <div className="relative aspect-[9/16] w-32 shrink-0 overflow-hidden rounded-xl bg-ink-800">
          {rendered ? (
            <video
              src={apiUrl(clip.render_url!)}
              poster={clip.thumb_url ? apiUrl(clip.thumb_url) : undefined}
              controls
              preload="none"
              className="h-full w-full object-cover"
            />
          ) : clip.thumb_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={apiUrl(clip.thumb_url)} alt="" className="h-full w-full object-cover opacity-70" />
          ) : (
            <div className="grid h-full place-items-center text-xs text-ink-100/30">
              {clip.render_status === "pending" || busy ? "rendering…" : "not rendered"}
            </div>
          )}
          <span className="absolute left-1.5 top-1.5 rounded-md bg-black/60 px-1.5 py-0.5 text-[10px]">
            #{rank}
          </span>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{clip.hook || clip.text.slice(0, 60)}</div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-100/45">
                <span className="pill capitalize">{clip.category}</span>
                <span>{fmtDuration(clip.duration)}</span>
                <span>·</span>
                <span>
                  {clip.start.toFixed(1)}s → {clip.end.toFixed(1)}s
                </span>
                {clip.llm_used && <span className="pill">AI-scored</span>}
                {!clip.self_contained && (
                  <span className="pill text-yellow-400">needs context</span>
                )}
              </div>
            </div>
            <div className="text-right">
              <div className={`text-2xl font-bold leading-none ${scoreColor(clip.score.overall)}`}>
                {clip.score.overall}
              </div>
              <div className="text-[10px] uppercase tracking-wide text-ink-100/35">
                potential
              </div>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-3 gap-x-3 gap-y-1.5">
            {SUBSCORES.map(([k, label]) => (
              <div key={k} className="text-[11px]">
                <div className="flex justify-between text-ink-100/45">
                  <span>{label}</span>
                  <span>{clip.score[k]}</span>
                </div>
                <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full bg-brand-500/70"
                    style={{ width: `${clip.score[k]}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          {clip.reason && (
            <p className="mt-3 line-clamp-2 text-[11px] italic text-ink-100/40">
              {clip.reason}
            </p>
          )}

          <div className="mt-3 flex flex-wrap gap-2">
            {rendered && (
              <a href={apiUrl(clip.download_url!)} className="btn-ghost !py-1.5 !text-xs" download>
                Download MP4
              </a>
            )}
            {clip.srt_url && (
              <a href={apiUrl(clip.srt_url)} className="btn-ghost !py-1.5 !text-xs" download>
                .srt
              </a>
            )}
            {clip.ass_url && (
              <a href={clip.ass_url} className="btn-ghost !py-1.5 !text-xs" download>
                .ass
              </a>
            )}
            <button
              className="btn-ghost !py-1.5 !text-xs"
              onClick={onRegenerate}
              disabled={busy}
            >
              {busy ? "Rendering…" : rendered ? "Regenerate" : "Render"}
            </button>
            <button className="btn-ghost !py-1.5 !text-xs" onClick={onEdit}>
              Edit
            </button>
            <button
              className="btn-ghost !py-1.5 !text-xs"
              onClick={() => setShowText((s) => !s)}
            >
              {showText ? "Hide" : "Transcript"}
            </button>
          </div>

          {showText && (
            <p className="mt-3 max-h-40 overflow-y-auto rounded-lg bg-black/20 p-3 text-xs leading-relaxed text-ink-100/70">
              {clip.text}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

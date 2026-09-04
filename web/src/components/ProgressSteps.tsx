"use client";

import type { Job } from "@/lib/types";

const STAGES: { key: string; label: string }[] = [
  { key: "prepare", label: "Preparing video" },
  { key: "audio", label: "Extracting audio" },
  { key: "transcription", label: "Transcribing" },
  { key: "candidates", label: "Finding candidate moments" },
  { key: "llm", label: "Scoring with local AI" },
  { key: "select", label: "Selecting & refining clips" },
  { key: "render", label: "Rendering shorts" },
];

export function ProgressSteps({ job }: { job: Job | null }) {
  const currentIdx = job ? STAGES.findIndex((s) => s.key === job.stage) : -1;
  const failed = job?.state === "failed";
  const done = job?.state === "completed";

  return (
    <div className="card p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="text-sm font-medium">
          {done
            ? "Done"
            : failed
              ? "Failed"
              : job?.message || "Working…"}
        </div>
        <div className="text-xs text-ink-100/40">
          {Math.round((job?.progress || 0) * 100)}%
        </div>
      </div>

      <div className="mb-5 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div
          className={`h-full transition-all ${failed ? "bg-red-500" : "bg-brand-500"}`}
          style={{ width: `${Math.round((job?.progress || (done ? 1 : 0)) * 100)}%` }}
        />
      </div>

      <ol className="space-y-2.5">
        {STAGES.map((s, i) => {
          const state =
            done || (currentIdx >= 0 && i < currentIdx)
              ? "done"
              : i === currentIdx
                ? failed
                  ? "failed"
                  : "active"
                : "pending";
          return (
            <li key={s.key} className="flex items-center gap-3 text-sm">
              <span
                className={`grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[11px] ${
                  state === "done"
                    ? "border-accent/40 bg-accent/15 text-accent"
                    : state === "active"
                      ? "border-brand-400/50 bg-brand-400/15 text-brand-400"
                      : state === "failed"
                        ? "border-red-400/50 bg-red-400/15 text-red-400"
                        : "border-white/10 text-ink-100/30"
                }`}
              >
                {state === "done" ? "✓" : state === "failed" ? "✕" : i + 1}
              </span>
              <span
                className={
                  state === "pending" ? "text-ink-100/35" : "text-ink-100/80"
                }
              >
                {s.label}
              </span>
              {state === "active" && (
                <span className="ml-auto text-[11px] text-ink-100/40">
                  {Math.round((job?.progress || 0) * 100)}%
                </span>
              )}
            </li>
          );
        })}
      </ol>

      {failed && job?.error && (
        <div className="mt-4 rounded-lg border border-red-400/30 bg-red-400/5 p-3 text-xs text-red-300">
          {job.error}
        </div>
      )}
    </div>
  );
}

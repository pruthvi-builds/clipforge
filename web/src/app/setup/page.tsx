"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SetupSummary } from "@/lib/types";

export default function SetupPage() {
  const [summary, setSummary] = useState<SetupSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api.setup().then(setSummary).catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Setup check</h1>
          <p className="mt-1 text-sm text-ink-100/50">
            {summary
              ? `${summary.platform}${summary.apple_silicon ? " · Apple Silicon" : ""}`
              : "Checking your environment…"}
          </p>
        </div>
        <button className="btn-ghost !text-xs" onClick={load}>
          Re-check
        </button>
      </div>

      {error && (
        <div className="card border-red-400/30 bg-red-400/5 p-4 text-sm text-red-300">
          {error}
        </div>
      )}

      {summary && (
        <>
          <div
            className={`card mb-6 p-4 text-sm ${
              summary.ready
                ? "border-accent/30 bg-accent/5 text-accent"
                : "border-yellow-400/30 bg-yellow-400/5 text-yellow-300"
            }`}
          >
            {summary.ready
              ? "Ready — core requirements satisfied. You can create a project."
              : "Not ready — install the items marked below. FFmpeg + a transcription backend are required; Ollama is optional."}
          </div>

          <div className="card divide-y divide-white/[0.06]">
            {summary.checks.map((c) => (
              <div key={c.name} className="flex gap-3 p-4">
                <span
                  className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full text-[11px] ${
                    c.ok
                      ? "bg-accent/15 text-accent"
                      : "bg-yellow-400/15 text-yellow-400"
                  }`}
                >
                  {c.ok ? "✓" : "!"}
                </span>
                <div className="min-w-0">
                  <div className="text-sm font-medium">{c.name}</div>
                  <div className="mt-0.5 break-words text-xs text-ink-100/50">
                    {c.detail}
                  </div>
                  {!c.ok && c.fix && (
                    <pre className="mt-2 overflow-x-auto rounded-lg bg-black/30 p-2 text-[11px] text-ink-100/70">
                      {c.fix}
                    </pre>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

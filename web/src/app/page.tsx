"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ProjectListItem } from "@/lib/types";
import { fmtDate, fmtDuration } from "@/lib/format";

const STATUS_STYLES: Record<string, string> = {
  completed: "text-accent border-accent/30 bg-accent/10",
  processing: "text-brand-400 border-brand-400/30 bg-brand-400/10",
  queued: "text-brand-400 border-brand-400/30 bg-brand-400/10",
  failed: "text-red-400 border-red-400/30 bg-red-400/10",
  uploaded: "text-ink-100/60 border-white/10 bg-white/5",
  created: "text-ink-100/60 border-white/10 bg-white/5",
};

export default function Dashboard() {
  const [projects, setProjects] = useState<ProjectListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api
      .listProjects()
      .then(setProjects)
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  return (
    <div>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Projects</h1>
          <p className="mt-1 text-sm text-ink-100/50">
            Turn long videos into short-form content.
          </p>
        </div>
        <Link href="/create" className="btn-primary">
          New project
        </Link>
      </div>

      {error && (
        <div className="card mb-6 border-red-400/30 bg-red-400/5 p-4 text-sm text-red-300">
          {error} — is the API running? <code>npm run api</code>
        </div>
      )}

      {projects === null ? (
        <div className="text-sm text-ink-100/40">Loading…</div>
      ) : projects.length === 0 ? (
        <div className="card grid place-items-center px-6 py-20 text-center">
          <div className="mb-3 text-4xl opacity-40">🎬</div>
          <h2 className="text-lg font-medium">No projects yet</h2>
          <p className="mt-1 max-w-sm text-sm text-ink-100/50">
            Upload a podcast, interview or talk and ClipForge will find the
            strongest short-form moments.
          </p>
          <Link href="/create" className="btn-primary mt-5">
            Create your first
          </Link>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <Link
              key={p.id}
              href={`/projects/${p.id}`}
              className="card group overflow-hidden transition-colors hover:border-white/20"
            >
              <div className="relative aspect-video w-full bg-ink-800">
                {p.thumbnail_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={p.thumbnail_url}
                    alt=""
                    className="h-full w-full object-cover opacity-90"
                  />
                ) : (
                  <div className="grid h-full place-items-center text-2xl opacity-20">
                    ▶
                  </div>
                )}
                <span
                  className={`absolute right-2 top-2 rounded-full border px-2 py-0.5 text-[11px] capitalize ${
                    STATUS_STYLES[p.status] || STATUS_STYLES.created
                  }`}
                >
                  {p.status}
                </span>
              </div>
              <div className="p-4">
                <div className="truncate text-sm font-medium">{p.name}</div>
                <div className="mt-1 flex items-center gap-2 text-[11px] text-ink-100/40">
                  <span>{fmtDuration(p.duration)}</span>
                  <span>·</span>
                  <span>{p.n_clips} clips</span>
                  <span>·</span>
                  <span>{fmtDate(p.created_at)}</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

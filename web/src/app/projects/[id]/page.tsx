"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiUrl, pollJob } from "@/lib/api";
import type { Clip, Job, Project } from "@/lib/types";
import { fmtDuration } from "@/lib/format";
import { ClipCard } from "@/components/ClipCard";
import { ClipEditor } from "@/components/ClipEditor";
import { ProgressSteps } from "@/components/ProgressSteps";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [editing, setEditing] = useState<Clip | null>(null);
  const [busyClip, setBusyClip] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stopPoll = useRef<() => void>();

  const load = useCallback(async () => {
    try {
      const [p, c] = await Promise.all([api.getProject(id), api.getClips(id)]);
      setProject(p);
      setClips(c);
    } catch (e: any) {
      setError(e.message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // keep polling while anything is in flight
  useEffect(() => {
    const active =
      project?.status === "processing" ||
      project?.status === "queued" ||
      clips.some((c) => c.render_status === "pending");
    if (!active) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [project?.status, clips, load]);

  function watchJob(jobId: string) {
    stopPoll.current?.();
    stopPoll.current = pollJob(jobId, (j) => {
      setJob(j);
      if (j.state === "completed" || j.state === "failed") {
        setBusyClip(null);
        load();
      }
    });
  }

  async function reanalyze(n: number) {
    setError(null);
    const { job_id } = await api.analyze(id, {
      n_clips: n,
      render: true,
      style: project?.style || "general",
      caption_style: "bold",
      reframe_mode: "smart_auto",
      force: false,
    });
    setJob({ id: job_id, kind: "full", state: "queued", progress: 0 });
    watchJob(job_id);
  }

  async function renderAll() {
    const { job_id } = await api.renderProject(id, {
      caption_style: "bold",
      reframe_mode: "smart_auto",
      use_captions: true,
      enhance_audio: true,
    });
    setJob({ id: job_id, kind: "render", state: "queued", progress: 0 });
    watchJob(job_id);
  }

  async function regenerate(clip: Clip, body: Record<string, unknown> = {}) {
    setBusyClip(clip.id);
    try {
      const { job_id } = await api.renderClip(clip.id, {
        caption_style: "bold",
        reframe_mode: "smart_auto",
        use_captions: true,
        enhance_audio: true,
        ...body,
      });
      watchJob(job_id);
    } catch (e: any) {
      setError(e.message);
      setBusyClip(null);
    }
  }

  async function remove() {
    if (!confirm("Delete this project and all its files?")) return;
    await api.deleteProject(id);
    router.push("/");
  }

  if (error && !project) {
    return (
      <div className="card border-red-400/30 bg-red-400/5 p-6 text-sm text-red-300">
        {error}
      </div>
    );
  }
  if (!project) return <div className="text-sm text-ink-100/40">Loading…</div>;

  const processing =
    project.status === "processing" || project.status === "queued";

  return (
    <div>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <Link href="/" className="text-xs text-ink-100/40 hover:text-ink-100">
            ← Projects
          </Link>
          <h1 className="mt-1 text-2xl font-semibold">{project.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-ink-100/45">
            {project.video && (
              <>
                <span>{fmtDuration(project.video.duration)}</span>
                <span>·</span>
                <span>
                  {project.video.width}×{project.video.height}
                </span>
                <span>·</span>
              </>
            )}
            <span className="capitalize">{project.style}</span>
            {project.transcript && (
              <>
                <span>·</span>
                <span>
                  {project.transcript.backend} / {project.transcript.model}
                </span>
                {project.transcript.has_word_ts ? (
                  <span className="pill">word-level captions</span>
                ) : (
                  <span className="pill text-yellow-400">segment captions</span>
                )}
              </>
            )}
          </div>
        </div>
        <button className="btn-ghost !text-xs" onClick={remove}>
          Delete
        </button>
      </div>

      {error && (
        <div className="card mb-4 border-red-400/30 bg-red-400/5 p-3 text-xs text-red-300">
          {error}
        </div>
      )}

      {project.error && project.status === "failed" && (
        <div className="card mb-4 border-red-400/30 bg-red-400/5 p-4 text-sm text-red-300">
          {project.error}
        </div>
      )}

      {(project.warnings || []).map((w, i) => (
        <div
          key={i}
          className="card mb-4 border-yellow-400/30 bg-yellow-400/5 p-4 text-sm text-yellow-200"
        >
          ⚠ {w}
        </div>
      ))}

      {(processing || (job && job.state !== "completed")) && (
        <div className="mb-6">
          <ProgressSteps job={job} />
        </div>
      )}

      {project.transcript_preview && (
        <div className="card mb-6 p-4">
          <div className="label">Transcript preview</div>
          <p className="line-clamp-3 text-sm text-ink-100/60">
            {project.transcript_preview}
          </p>
          <Link
            href={apiUrl(`/api/projects/${id}/transcript`)}
            target="_blank"
            className="mt-2 inline-block text-[11px] text-brand-400 hover:underline"
          >
            View full transcript JSON →
          </Link>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">
          {clips.length} clip{clips.length === 1 ? "" : "s"}
        </span>
        <div className="ml-auto flex gap-2">
          <button className="btn-ghost !text-xs" onClick={() => reanalyze(3)} disabled={processing}>
            Generate Top 3
          </button>
          <button className="btn-ghost !text-xs" onClick={() => reanalyze(5)} disabled={processing}>
            Top 5
          </button>
          <button className="btn-ghost !text-xs" onClick={() => reanalyze(10)} disabled={processing}>
            Top 10
          </button>
          {clips.length > 0 && (
            <button className="btn-primary !text-xs" onClick={renderAll} disabled={processing}>
              Re-render all
            </button>
          )}
        </div>
      </div>

      {clips.length === 0 && !processing ? (
        <div className="card grid place-items-center px-6 py-16 text-center text-sm text-ink-100/50">
          No clips yet.
          <button className="btn-primary mt-4" onClick={() => reanalyze(5)}>
            Find clips
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {clips
            .slice()
            .sort((a, b) => b.score.overall - a.score.overall)
            .map((clip, i) => (
              <ClipCard
                key={clip.id}
                clip={clip}
                rank={i + 1}
                busy={busyClip === clip.id}
                onEdit={() => setEditing(clip)}
                onRegenerate={() => regenerate(clip, { force: true })}
              />
            ))}
        </div>
      )}

      {editing && (
        <ClipEditor
          clip={editing}
          onClose={() => setEditing(null)}
          onApply={(body) => {
            regenerate(editing, body);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

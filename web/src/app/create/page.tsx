"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { api, pollJob } from "@/lib/api";
import type { Job } from "@/lib/types";
import { UploadDropzone } from "@/components/UploadDropzone";
import { ProgressSteps } from "@/components/ProgressSteps";
import { fmtBytes, fmtDuration } from "@/lib/format";

type Phase = "upload" | "configure" | "processing";

type Opt = [string, string];
const STYLES = ["general", "educational", "podcast", "story", "interview"];
const LENGTHS = ["auto", "15", "30", "45", "60", "90"];
const REFRAMES: Opt[] = [
  ["fit", "Fit (no crop)"],
  ["smart_auto", "Smart Auto"],
  ["center", "Center"],
  ["face", "Face Tracking"],
  ["speaker", "Speaker Tracking"],
];
const CAPTIONS = ["bold", "clean", "karaoke", "minimal", "highlight"];
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

export default function CreatePage() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("upload");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [meta, setMeta] = useState<{ duration: number; width: number; height: number; size_bytes: number } | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const stopPoll = useRef<() => void>();

  const [cfg, setCfg] = useState({
    n_clips: 5,
    clip_length: "auto",
    style: "general",
    use_llm: true,
    use_captions: true,
    caption_style: "bold",
    reframe_mode: "fit",
    enhance_audio: true,
  });

  async function handleFile(file: File) {
    setError(null);
    setFileName(file.name);
    setUploadPct(0);
    try {
      const { id } = await api.createProject(file.name.replace(/\.[^.]+$/, ""), cfg.style);
      setProjectId(id);
      const res = await api.uploadVideo(id, file, setUploadPct);
      setMeta(res.meta as any);
      setUploadPct(null);
      setPhase("configure");
    } catch (e: any) {
      setError(e.message);
      setUploadPct(null);
    }
  }

  async function createShorts() {
    if (!projectId) return;
    setError(null);
    setPhase("processing");
    try {
      const { job_id } = await api.analyze(projectId, { ...cfg, render: true });
      stopPoll.current = pollJob(job_id, (j) => {
        setJob(j);
        if (j.state === "completed") {
          setTimeout(() => router.push(`/projects/${projectId}`), 700);
        }
        if (j.state === "failed") setError(j.error || "Processing failed");
      });
    } catch (e: any) {
      setError(e.message);
      setPhase("configure");
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-1 text-2xl font-semibold">Create shorts</h1>
      <p className="mb-8 text-sm text-ink-100/50">
        Everything runs locally on your machine. No uploads leave your computer.
      </p>

      {error && (
        <div className="card mb-6 border-red-400/30 bg-red-400/5 p-4 text-sm text-red-300">
          {error}
        </div>
      )}

      {phase === "upload" && (
        <UploadDropzone onFile={handleFile} progress={uploadPct} fileName={fileName} />
      )}

      {phase === "configure" && meta && (
        <div className="space-y-6">
          <div className="card flex items-center gap-4 p-4">
            <div className="grid h-14 w-24 shrink-0 place-items-center rounded-lg bg-ink-800 text-xl opacity-30">
              ▶
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{fileName}</div>
              <div className="mt-0.5 text-[11px] text-ink-100/40">
                {fmtDuration(meta.duration)} · {meta.width}×{meta.height} ·{" "}
                {fmtBytes(meta.size_bytes)}
              </div>
            </div>
          </div>

          <div className="card space-y-5 p-5">
            <Segmented
              label="Desired clips"
              value={String(cfg.n_clips)}
              options={[["3", "3"], ["5", "5"], ["10", "10"]] as Opt[]}
              onChange={(v) => setCfg({ ...cfg, n_clips: Number(v) })}
            />
            <Segmented
              label="Clip length"
              value={cfg.clip_length}
              options={LENGTHS.map((l): Opt => [l, l === "auto" ? "Auto" : `${l}s`])}
              onChange={(v) => setCfg({ ...cfg, clip_length: v })}
            />
            <Segmented
              label="Clip style"
              value={cfg.style}
              options={STYLES.map((s): Opt => [s, cap(s)])}
              onChange={(v) => setCfg({ ...cfg, style: v })}
            />
            <Segmented
              label="Reframe"
              value={cfg.reframe_mode}
              options={REFRAMES}
              onChange={(v) => setCfg({ ...cfg, reframe_mode: v })}
            />
            <div className="grid gap-5 sm:grid-cols-2">
              <Segmented
                label="Captions"
                value={cfg.use_captions ? "on" : "off"}
                options={[["on", "On"], ["off", "Off"]] as Opt[]}
                onChange={(v) => setCfg({ ...cfg, use_captions: v === "on" })}
              />
              <Segmented
                label="Caption style"
                value={cfg.caption_style}
                options={CAPTIONS.map((c): Opt => [c, cap(c)])}
                onChange={(v) => setCfg({ ...cfg, caption_style: v })}
              />
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              <Toggle
                label="Use local AI (Ollama)"
                hint="Falls back to heuristics if unavailable"
                checked={cfg.use_llm}
                onChange={(v) => setCfg({ ...cfg, use_llm: v })}
              />
              <Toggle
                label="Enhance audio"
                hint="Loudness + light noise reduction"
                checked={cfg.enhance_audio}
                onChange={(v) => setCfg({ ...cfg, enhance_audio: v })}
              />
            </div>
          </div>

          <button className="btn-primary w-full" onClick={createShorts}>
            Create shorts
          </button>
        </div>
      )}

      {phase === "processing" && (
        <div className="space-y-4">
          <ProgressSteps job={job} />
          <p className="text-center text-xs text-ink-100/40">
            The first run downloads the Whisper model — later runs are much
            faster. Keep the worker (<code>npm run worker</code>) running.
          </p>
        </div>
      )}
    </div>
  );
}

function Segmented({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: [string, string][];
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {options.map(([v, l]) => (
          <button
            key={v}
            onClick={() => onChange(v)}
            className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
              value === v
                ? "border-brand-500 bg-brand-500/15 text-white"
                : "border-white/10 bg-white/[0.02] text-ink-100/60 hover:bg-white/[0.06]"
            }`}
          >
            {l}
          </button>
        ))}
      </div>
    </div>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className="flex items-center gap-3 text-left"
    >
      <span
        className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
          checked ? "bg-brand-500" : "bg-white/15"
        }`}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${
            checked ? "left-4" : "left-0.5"
          }`}
        />
      </span>
      <span>
        <span className="block text-sm">{label}</span>
        {hint && <span className="block text-[11px] text-ink-100/40">{hint}</span>}
      </span>
    </button>
  );
}

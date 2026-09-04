"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type S = Record<string, any>;

const FIELDS: {
  section: string;
  items: { key: string; label: string; type: "text" | "number" | "select" | "bool"; options?: string[]; hint?: string }[];
}[] = [
  {
    section: "Video processing",
    items: [
      { key: "whisper_model", label: "Whisper model", type: "select", options: ["tiny", "base", "small", "medium", "large-v3"] },
      { key: "whisper_backend", label: "Backend", type: "select", options: ["auto", "faster-whisper", "whisper.cpp"] },
      { key: "output_width", label: "Output width", type: "number" },
      { key: "output_height", label: "Output height", type: "number" },
      { key: "output_fps", label: "Output FPS", type: "number" },
      { key: "video_crf", label: "Video CRF (lower = higher quality)", type: "number" },
      { key: "default_clips", label: "Default number of clips", type: "number" },
      { key: "default_clip_length", label: "Default clip length", type: "select", options: ["auto", "15", "30", "45", "60", "90"] },
      { key: "enhance_audio", label: "Enhance audio by default", type: "bool" },
    ],
  },
  {
    section: "AI (local LLM)",
    items: [
      { key: "ollama_base_url", label: "Ollama URL", type: "text", hint: "http://localhost:11434" },
      { key: "model_name", label: "LLM model", type: "text", hint: "qwen2.5:7b · llama3.1:8b · mistral:7b" },
      { key: "llm_temperature", label: "Temperature", type: "number" },
      { key: "llm_max_tokens", label: "Max tokens", type: "number" },
    ],
  },
  {
    section: "Captions",
    items: [
      { key: "caption_style", label: "Default style", type: "select", options: ["clean", "bold", "karaoke", "minimal", "highlight"] },
      { key: "reframe_mode", label: "Default reframe", type: "select", options: ["smart_auto", "center", "face", "speaker"] },
      { key: "use_ai_hooks", label: "Use AI-generated hooks", type: "bool" },
    ],
  },
  {
    section: "Processing",
    items: [
      { key: "min_clip_seconds", label: "Min clip seconds", type: "number" },
      { key: "max_clip_seconds", label: "Max clip seconds", type: "number" },
      { key: "boundary_padding", label: "Boundary padding (s)", type: "number" },
      { key: "worker_concurrency", label: "Worker processes", type: "number" },
    ],
  },
];

export default function SettingsPage() {
  const [settings, setSettings] = useState<S | null>(null);
  const [dirty, setDirty] = useState<S>({});
  const [models, setModels] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then(setSettings).catch((e) => setError(e.message));
    api.ollamaModels().then((r) => setModels(r.models)).catch(() => {});
  }, []);

  function set(key: string, value: any) {
    setDirty((d) => ({ ...d, [key]: value }));
    setSaved(false);
  }

  async function save() {
    try {
      await api.saveSettings(dirty);
      setSaved(true);
      setDirty({});
      setSettings(await api.getSettings());
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (!settings) return <div className="text-sm text-ink-100/40">Loading…</div>;

  const val = (k: string) => (k in dirty ? dirty[k] : settings[k]);

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-1 text-2xl font-semibold">Settings</h1>
      <p className="mb-8 text-sm text-ink-100/50">
        Saved to the local database and applied on the next job.
      </p>

      {error && (
        <div className="card mb-4 border-red-400/30 bg-red-400/5 p-3 text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="space-y-6">
        {FIELDS.map((sec) => (
          <div key={sec.section} className="card p-5">
            <h2 className="mb-4 text-sm font-semibold">{sec.section}</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {sec.items.map((f) => {
                const options =
                  f.key === "model_name" && models.length
                    ? models
                    : f.options;
                return (
                  <label key={f.key} className="block">
                    <span className="label">{f.label}</span>
                    {f.type === "bool" ? (
                      <button
                        type="button"
                        onClick={() => set(f.key, !val(f.key))}
                        className={`mt-1 h-5 w-9 rounded-full transition-colors ${
                          val(f.key) ? "bg-brand-500" : "bg-white/15"
                        } relative`}
                      >
                        <span
                          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${
                            val(f.key) ? "left-4" : "left-0.5"
                          }`}
                        />
                      </button>
                    ) : f.key === "model_name" && models.length ? (
                      <select
                        className="input"
                        value={val(f.key) ?? ""}
                        onChange={(e) => set(f.key, e.target.value)}
                      >
                        {options!.map((o) => (
                          <option key={o} value={o}>
                            {o}
                          </option>
                        ))}
                      </select>
                    ) : f.type === "select" ? (
                      <select
                        className="input"
                        value={String(val(f.key) ?? "")}
                        onChange={(e) => set(f.key, e.target.value)}
                      >
                        {options!.map((o) => (
                          <option key={o} value={o}>
                            {o}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        className="input"
                        type={f.type}
                        value={val(f.key) ?? ""}
                        onChange={(e) =>
                          set(
                            f.key,
                            f.type === "number"
                              ? Number(e.target.value)
                              : e.target.value,
                          )
                        }
                      />
                    )}
                    {f.hint && (
                      <span className="mt-1 block text-[11px] text-ink-100/35">
                        {f.hint}
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="sticky bottom-4 mt-6 flex items-center justify-end gap-3">
        {saved && <span className="text-xs text-accent">Saved ✓</span>}
        <button
          className="btn-primary"
          onClick={save}
          disabled={Object.keys(dirty).length === 0}
        >
          Save changes
        </button>
      </div>
    </div>
  );
}

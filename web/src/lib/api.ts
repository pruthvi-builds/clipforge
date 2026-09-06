import type {
  Clip,
  Job,
  Project,
  ProjectListItem,
  SetupSummary,
} from "./types";

// Locally the browser talks to the Next.js origin and next.config.js rewrites
// /api/* to the FastAPI backend. In production (no local Next.js server to do
// the rewrite) NEXT_PUBLIC_API_URL points straight at the deployed API so
// uploads aren't funneled through a serverless proxy.
const BASE = process.env.NEXT_PUBLIC_API_URL || "";

// Prefix a server-issued relative path (e.g. clip.download_url) with the API
// origin so it resolves correctly when the web app and API are on different
// hosts (production), while staying a plain relative path in local dev.
export function apiUrl(path: string): string {
  return BASE + path;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: {
      ...(init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const msg =
      data?.error?.message || data?.detail || `Request failed (${res.status})`;
    const err = new Error(msg) as Error & { hint?: string };
    err.hint = data?.error?.hint;
    throw err;
  }
  return data as T;
}

async function uploadChunked(
  id: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<{ meta: Project["video"] & { path: string } }> {
  const start = await req<{ received: number; chunk_size: number }>(
    `/api/projects/${id}/upload/chunked/start`,
    { method: "POST", body: JSON.stringify({ filename: file.name, size: file.size }) },
  );
  const chunkSize = start.chunk_size || 4 * 1024 * 1024;
  let sent = start.received || 0; // resume point if a prior attempt was interrupted

  while (sent < file.size) {
    const end = Math.min(sent + chunkSize, file.size);
    const slice = file.slice(sent, end);
    let attempt = 0;
    for (;;) {
      try {
        const res = await fetch(apiUrl(`/api/projects/${id}/upload/chunked`), {
          method: "PATCH",
          headers: { "X-Offset": String(sent), "Content-Type": "application/octet-stream" },
          body: slice,
        });
        if (res.status === 409) {
          // Server has a different amount stored — resync and continue from there.
          const info = await res.json().catch(() => null);
          const at = info?.error?.received;
          if (typeof at === "number") { sent = at; break; }
          throw new Error("Upload out of sync");
        }
        if (!res.ok) {
          const data = await res.json().catch(() => null);
          throw new Error(data?.error?.message || `Chunk failed (${res.status})`);
        }
        const data = (await res.json()) as { received: number };
        sent = data.received;
        break;
      } catch (e) {
        if (++attempt >= 4) throw e;
        await new Promise((r) => setTimeout(r, 1000 * attempt));
      }
    }
    if (onProgress) onProgress(Math.round((sent / file.size) * 100));
  }

  return req<{ meta: Project["video"] & { path: string } }>(
    `/api/projects/${id}/upload/chunked/finish`,
    { method: "POST" },
  );
}

export const api = {
  health: () => req<{ ok: boolean; version: string }>("/api/health"),
  setup: () => req<SetupSummary>("/api/setup"),

  getSettings: () => req<Record<string, unknown>>("/api/settings"),
  saveSettings: (values: Record<string, unknown>) =>
    req<{ saved: Record<string, unknown> }>("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ values }),
    }),
  ollamaModels: () =>
    req<{ reachable: boolean; models: string[]; base_url: string; selected?: string }>(
      "/api/ollama/models",
    ),

  listProjects: () =>
    req<{ projects: ProjectListItem[] }>("/api/projects").then((r) => r.projects),
  createProject: (name: string, style: string) =>
    req<{ id: string }>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name, style }),
    }),
  getProject: (id: string) => req<Project>(`/api/projects/${id}`),
  deleteProject: (id: string) =>
    req<{ deleted: string }>(`/api/projects/${id}`, { method: "DELETE" }),

  uploadVideo: (id: string, file: File, onProgress?: (pct: number) => void) => {
    // Small files: one POST. Larger files: sequential chunks, because some
    // tunnels cap or badly throttle a single large request body. Chunks are
    // also resumable if one fails mid-way.
    const CHUNK_THRESHOLD = 6 * 1024 * 1024;
    if (file.size <= CHUNK_THRESHOLD) {
      return new Promise<{ meta: Project["video"] & { path: string } }>((resolve, reject) => {
        const form = new FormData();
        form.append("file", file);
        const xhr = new XMLHttpRequest();
        xhr.open("POST", apiUrl(`/api/projects/${id}/upload`));
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable && onProgress)
            onProgress(Math.round((e.loaded / e.total) * 100));
        };
        xhr.onload = () => {
          try {
            const data = JSON.parse(xhr.responseText || "{}");
            if (xhr.status >= 200 && xhr.status < 300) resolve(data);
            else reject(new Error(data?.error?.message || `Upload failed (${xhr.status})`));
          } catch (e) {
            reject(e);
          }
        };
        xhr.onerror = () => reject(new Error("Network error during upload"));
        xhr.send(form);
      });
    }
    return uploadChunked(id, file, onProgress);
  },

  analyze: (id: string, body: Record<string, unknown>) =>
    req<{ job_id: string; kind: string }>(`/api/projects/${id}/analyze`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  renderProject: (id: string, body: Record<string, unknown>) =>
    req<{ job_id: string }>(`/api/projects/${id}/render`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getClips: (id: string) =>
    req<{ clips: Clip[] }>(`/api/projects/${id}/clips`).then((r) => r.clips),
  renderClip: (clipId: string, body: Record<string, unknown>) =>
    req<{ job_id: string }>(`/api/clips/${clipId}/render`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getJob: (jobId: string) => req<Job>(`/api/jobs/${jobId}`),
};

export function pollJob(
  jobId: string,
  onUpdate: (job: Job) => void,
  intervalMs = 1000,
): () => void {
  let stopped = false;
  const tick = async () => {
    if (stopped) return;
    try {
      const job = await api.getJob(jobId);
      onUpdate(job);
      if (job.state === "completed" || job.state === "failed") return;
    } catch {
      /* keep polling; worker or API may be briefly busy */
    }
    if (!stopped) setTimeout(tick, intervalMs);
  };
  tick();
  return () => {
    stopped = true;
  };
}

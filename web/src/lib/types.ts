export interface VideoMeta {
  path: string;
  duration: number;
  width: number;
  height: number;
  fps: number;
  has_audio: boolean;
  video_codec: string;
  audio_codec: string;
  size_bytes: number;
  container: string;
}

export interface ClipScore {
  engagement: number;
  hook: number;
  clarity: number;
  self_contained: number;
  emotion: number;
  novelty: number;
  story: number;
  actionability: number;
  audio_quality: number;
  overall: number;
}

export interface Clip {
  id: string;
  project_id: string;
  idx: number;
  start: number;
  end: number;
  duration: number;
  category: string;
  hook: string;
  alt_hook: string;
  opening_text: string;
  reason: string;
  self_contained: boolean;
  score: ClipScore;
  text: string;
  emphasis_words: string[];
  llm_used: boolean;
  render_status: string;
  render_url?: string | null;
  thumb_url?: string | null;
  srt_url?: string | null;
  ass_url?: string | null;
  download_url?: string | null;
}

export interface Project {
  id: string;
  name: string;
  status: string;
  style: string;
  created_at: number;
  updated_at: number;
  error?: string | null;
  video?: {
    filename: string;
    duration: number;
    width: number;
    height: number;
    fps: number;
    has_audio: number;
    size_bytes: number;
  } | null;
  transcript?: {
    language: string;
    backend: string;
    model: string;
    has_word_ts: number;
    n_segments: number;
  } | null;
  clips: Clip[];
  media?: { original_url: string | null };
  transcript_preview?: string;
  warnings?: string[];
}

export interface ProjectListItem {
  id: string;
  name: string;
  status: string;
  style: string;
  created_at: number;
  filename?: string;
  duration?: number;
  width?: number;
  height?: number;
  n_clips: number;
  thumbnail_url?: string | null;
}

export interface Job {
  id: string;
  kind: string;
  state: "queued" | "processing" | "completed" | "failed";
  stage?: string;
  progress: number;
  message?: string;
  error?: string;
}

export interface SetupCheck {
  name: string;
  ok: boolean;
  detail: string;
  fix: string;
}

export interface SetupSummary {
  ready: boolean;
  apple_silicon: boolean;
  platform: string;
  checks: SetupCheck[];
}

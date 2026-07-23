export interface Video {
  id: string;
  name: string;
  source: "upload" | "link";
  size_bytes: number;
  duration: number;
  width: number;
  height: number;
  fps: number;
  codec: string;
  thumbnail_path: string;
  status: "downloading" | "ready" | "error";
  progress: number;
  error: string;
  created_at: string;
}

export interface Overlay {
  text: string;
  y: number; // 0 (top) .. 1 (bottom)
  size: "small" | "medium" | "large";
}

export interface SplitOptions {
  mode: "count" | "duration" | "best";
  count: number;
  duration_seconds: number;
  best_count: number;
  clip_length: number;
  aspect: "source" | "reel";
  reel_fill: "crop" | "fit";
  overlays: Overlay[];
  quality: "low" | "medium" | "high" | "best";
  resolution: "source" | "1080" | "720" | "480";
  format: "mp4" | "mov" | "webm";
  ai_titles: boolean;
  subtitles: boolean;
  subtitle_y: number;
  transcription: "auto" | "cloud" | "local";
  output_mode: "none" | "local" | "drive";
  output_dir: string;
  drive_folder_id: string;
}

export interface Part {
  id: string;
  job_id: string;
  index: number;
  label: string;
  overlays: Overlay[];
  title: string;
  path: string;
  thumbnail_path: string;
  start_time: number;
  end_time: number;
  duration: number;
  size_bytes: number;
  status: "pending" | "rendering" | "ready" | "error";
  transcript: string;
  subtitles: { start: number; end: number; text: string }[];
  viral_score: number;
  viral_hook: number;
  viral_reason: string;
  viral_tier: "" | "ai" | "heuristic" | "signal";
  export_status: "none" | "saving" | "saved" | "error";
  export_target: string;
  export_error: string;
  created_at: string;
}

export interface Job {
  id: string;
  video_id: string;
  options: Partial<SplitOptions>;
  status: "queued" | "running" | "done" | "error" | "cancelled";
  progress: number;
  message: string;
  error: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobDetail extends Job {
  video: Video;
  parts: Part[];
}

export interface AppSettings {
  output_mode: "none" | "local" | "drive";
  output_dir: string;
  drive_folder_id: string;
  label_template: string;
  label_y: number;
  label_size: "small" | "medium" | "large";
  aspect: "source" | "reel";
  reel_fill: "crop" | "fit";
  subtitles: boolean;
  subtitle_y: number;
  transcription_mode: "auto" | "cloud" | "local";
  quality: "low" | "medium" | "high" | "best";
  resolution: "source" | "1080" | "720" | "480";
  format: "mp4" | "mov" | "webm";
}

export interface DriveStatus {
  configured: boolean;
  connected: boolean;
  account_email: string;
}

export interface DriveFolder {
  id: string;
  name: string;
}

export interface AiStatus {
  provider: string;
  has_key: boolean;
  model: string;
  stt_model: string;
  ok: boolean;
  message: string;
  whisper_available: boolean;
  cloud_stt_available: boolean;
}

export interface FolderCheckResult {
  ok: boolean;
  resolved: string;
  message: string;
}

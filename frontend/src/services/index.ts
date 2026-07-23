import { api } from "@/lib/api";
import type {
  AiStatus,
  AppSettings,
  DriveFolder,
  DriveStatus,
  FolderCheckResult,
  JobDetail,
  Part,
  SplitOptions,
  Video,
} from "@/types";

export const videos = {
  get: (id: string) => api<Video>(`/api/videos/${id}`),
  fromLink: (url: string) =>
    api<Video>("/api/videos/link", { method: "POST", body: JSON.stringify({ url }) }),
  remove: (id: string) => api<void>(`/api/videos/${id}`, { method: "DELETE" }),
};

export const jobs = {
  create: (video_id: string, options: SplitOptions) =>
    api<JobDetail>("/api/jobs", {
      method: "POST",
      body: JSON.stringify({ video_id, options }),
    }),
  get: (id: string) => api<JobDetail>(`/api/jobs/${id}`),
  cancel: (id: string) => api<void>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  remove: (id: string) => api<void>(`/api/jobs/${id}`, { method: "DELETE" }),
};

export const parts = {
  update: (id: string, patch: { label?: string; title?: string }) =>
    api<Part>(`/api/parts/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  remove: (id: string) => api<void>(`/api/parts/${id}`, { method: "DELETE" }),
  export: (part_ids: string[], mode: "local" | "drive", destination: string) =>
    api<{ started: number }>("/api/parts/export", {
      method: "POST",
      body: JSON.stringify({
        part_ids,
        mode,
        output_dir: mode === "local" ? destination : "",
        drive_folder_id: mode === "drive" ? destination : "root",
      }),
    }),
};

export const settings = {
  get: () => api<AppSettings>("/api/settings"),
  update: (patch: Partial<AppSettings>) =>
    api<AppSettings>("/api/settings", { method: "PUT", body: JSON.stringify(patch) }),
  checkFolder: (path: string) =>
    api<FolderCheckResult>("/api/settings/check-folder", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
};

export const ai = {
  status: () => api<AiStatus>("/api/ai/status"),
};

export const drive = {
  status: () => api<DriveStatus>("/api/drive/status"),
  authUrl: () => api<{ url: string }>("/api/drive/auth-url"),
  disconnect: () => api<void>("/api/drive/disconnect", { method: "POST" }),
  folders: () => api<DriveFolder[]>("/api/drive/folders"),
  createFolder: (name: string, parent = "root") =>
    api<DriveFolder>("/api/drive/folders", {
      method: "POST",
      body: JSON.stringify({ name, parent }),
    }),
};

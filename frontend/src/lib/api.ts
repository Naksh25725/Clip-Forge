export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const fetcher = <T>(path: string) => api<T>(path);

/** Absolute URL for a backend-relative /media/... path. */
export function mediaUrl(path: string): string {
  if (!path) return "";
  return path.startsWith("http") ? path : `${API_URL}${path}`;
}

export function partDownloadUrl(partId: string): string {
  return `${API_URL}/api/parts/${partId}/download`;
}

export function errorMessage(e: unknown, fallback = "Something went wrong"): string {
  return e instanceof Error ? e.message : fallback;
}

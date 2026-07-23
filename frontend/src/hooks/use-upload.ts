"use client";

import { useCallback, useRef, useState } from "react";
import { API_URL } from "@/lib/api";
import type { Video } from "@/types";

export interface UploadItem {
  id: string;
  file: File;
  progress: number;
  status: "uploading" | "done" | "error" | "cancelled";
  error?: string;
  video?: Video;
}

/** Multi-file uploader with real progress + cancel, built on XHR
 * (fetch has no upload progress events). */
export function useUpload(onComplete?: (video: Video) => void) {
  const [items, setItems] = useState<UploadItem[]>([]);
  const xhrs = useRef(new Map<string, XMLHttpRequest>());

  const update = useCallback((id: string, patch: Partial<UploadItem>) => {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)));
  }, []);

  const upload = useCallback(
    (files: File[]) => {
      for (const file of files) {
        const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        setItems((prev) => [...prev, { id, file, progress: 0, status: "uploading" }]);

        const xhr = new XMLHttpRequest();
        xhrs.current.set(id, xhr);

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) update(id, { progress: (e.loaded / e.total) * 100 });
        };
        xhr.onload = () => {
          xhrs.current.delete(id);
          if (xhr.status >= 200 && xhr.status < 300) {
            const video = JSON.parse(xhr.responseText) as Video;
            update(id, { status: "done", progress: 100, video });
            onComplete?.(video);
          } else {
            let message = `Upload failed (${xhr.status})`;
            try {
              message = JSON.parse(xhr.responseText)?.detail ?? message;
            } catch {
              /* keep default */
            }
            update(id, { status: "error", error: message });
          }
        };
        xhr.onerror = () => {
          xhrs.current.delete(id);
          update(id, { status: "error", error: "Network error" });
        };
        xhr.onabort = () => {
          xhrs.current.delete(id);
          update(id, { status: "cancelled" });
        };

        const form = new FormData();
        form.append("file", file);
        xhr.open("POST", `${API_URL}/api/videos/upload`);
        xhr.send(form);
      }
    },
    [onComplete, update],
  );

  const cancel = useCallback((id: string) => {
    xhrs.current.get(id)?.abort();
  }, []);

  const clearFinished = useCallback(() => {
    setItems((prev) => prev.filter((it) => it.status === "uploading"));
  }, []);

  return { items, upload, cancel, clearFinished };
}

"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  Film,
  Link2,
  Loader2,
  UploadCloud,
  X,
} from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { useUpload } from "@/hooks/use-upload";
import { errorMessage, mediaUrl } from "@/lib/api";
import { formatBytes, formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";
import * as services from "@/services";
import type { Video } from "@/types";

const ACCEPT = ".mp4,.mov,.mkv,.avi,.webm,.m4v";

export function SourcePanel({
  video,
  onVideo,
  onClear,
  disabled,
}: {
  video: Video | null;
  onVideo: (video: Video) => void;
  onClear: () => void;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [link, setLink] = useState("");
  const [importing, setImporting] = useState(false);

  const { items, upload, cancel } = useUpload((uploaded) => {
    onVideo(uploaded);
    toast.success("Video ready");
  });
  const active = items.find((i) => i.status === "uploading");

  const handleFiles = useCallback(
    (list: FileList | null) => {
      if (!list?.length) return;
      upload([list[0]]); // one source video at a time
    },
    [upload],
  );

  const importLink = async () => {
    if (!link.trim()) return;
    setImporting(true);
    try {
      const started = await services.videos.fromLink(link.trim());
      onVideo(started);
      setLink("");
      toast.info("Downloading from link…");
    } catch (e) {
      toast.error(errorMessage(e, "Could not start the download"));
    } finally {
      setImporting(false);
    }
  };

  // A source is loaded — show it instead of the pickers.
  if (video) {
    const downloading = video.status === "downloading";
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl p-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="relative h-20 w-32 shrink-0 overflow-hidden rounded-xl bg-black/40">
            {video.thumbnail_path ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={mediaUrl(video.thumbnail_path)} alt="" className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full items-center justify-center">
                {downloading ? (
                  <Loader2 className="h-5 w-5 animate-spin text-violet-300" />
                ) : (
                  <Film className="h-5 w-5 text-muted-foreground" />
                )}
              </div>
            )}
          </div>

          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{video.name}</p>
            {video.status === "error" ? (
              <p className="mt-1 flex items-center gap-1.5 text-sm text-red-400">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> {video.error}
              </p>
            ) : downloading ? (
              <div className="mt-2 max-w-sm">
                <Progress value={video.progress} className="h-1.5" />
                <p className="mt-1 text-xs text-muted-foreground">
                  Downloading… {Math.round(video.progress)}%
                </p>
              </div>
            ) : (
              <p className="mt-0.5 text-sm text-muted-foreground">
                {formatDuration(video.duration)} · {video.width}×{video.height} ·{" "}
                {video.fps ? `${video.fps}fps · ` : ""}
                {video.codec.toUpperCase()} · {formatBytes(video.size_bytes)}
              </p>
            )}
          </div>

          <Button variant="ghost" size="sm" onClick={onClear} disabled={disabled}>
            <X /> Change
          </Button>
        </div>
      </motion.div>
    );
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => !active && inputRef.current?.click()}
        className={cn(
          "glass group flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-all",
          dragging
            ? "glow border-primary/70 bg-primary/[0.07]"
            : "border-white/[0.08] hover:border-primary/40 hover:bg-white/[0.04]",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <div
          className={cn(
            "mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500/20 to-fuchsia-500/20 transition-transform",
            dragging ? "scale-110" : "group-hover:scale-105",
          )}
        >
          <UploadCloud className="h-5 w-5 text-violet-300" />
        </div>
        <p className="font-medium">{dragging ? "Drop it" : "Drop a video here"}</p>
        <p className="mt-0.5 text-sm text-muted-foreground">
          or <span className="text-violet-300 underline underline-offset-2">browse</span> — MP4, MOV,
          MKV, AVI, WEBM
        </p>
      </div>

      <AnimatePresence>
        {active && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="glass flex items-center gap-3 rounded-xl p-3"
          >
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-violet-300" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm">{active.file.name}</p>
              <Progress value={active.progress} className="mt-1.5 h-1.5" />
            </div>
            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
              {Math.round(active.progress)}%
            </span>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => cancel(active.id)}>
              <X />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex items-center gap-3">
        <span className="h-px flex-1 bg-white/[0.08]" />
        <span className="text-xs uppercase tracking-wide text-muted-foreground/60">or</span>
        <span className="h-px flex-1 bg-white/[0.08]" />
      </div>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <Link2 className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={link}
            onChange={(e) => setLink(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && importLink()}
            placeholder="Paste a Google Drive link…"
            className="pl-9"
          />
        </div>
        <Button onClick={importLink} disabled={!link.trim() || importing}>
          {importing ? <Loader2 className="animate-spin" /> : <Link2 />} Import
        </Button>
      </div>
      <p className="text-xs text-muted-foreground/70">
        Drive links must be shared as “Anyone with the link”, or connect your Google account below to
        pull private files.
      </p>
    </div>
  );
}

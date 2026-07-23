"use client";

import { motion } from "framer-motion";
import {
  AlertTriangle,
  Check,
  CloudUpload,
  Download,
  Flame,
  FolderOpen,
  Loader2,
  Play,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { errorMessage, mediaUrl, partDownloadUrl } from "@/lib/api";
import { formatBytes, formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";
import * as services from "@/services";
import type { Part } from "@/types";

function scoreTone(score: number): string {
  if (score >= 70) return "bg-emerald-500/85 text-white";
  if (score >= 45) return "bg-amber-500/85 text-black";
  return "bg-zinc-700/85 text-zinc-100";
}

const TIER_LABEL: Record<string, string> = {
  ai: "Rated by AI",
  heuristic: "Rated from transcript",
  signal: "Rated from audio & motion",
};

export function PartCard({
  part,
  onChanged,
  index = 0,
}: {
  part: Part;
  onChanged: () => void;
  index?: number;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(part.label);
  const [preview, setPreview] = useState(false);
  const [saving, setSaving] = useState(false);

  const busy = part.status === "rendering" || part.status === "pending";

  const saveLabel = async () => {
    const next = draft.trim();
    if (next === part.label) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await services.parts.update(part.id, { label: next });
      toast.info("Re-rendering with the new text…");
      setEditing(false);
      onChanged();
    } catch (e) {
      toast.error(errorMessage(e, "Could not rename"));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    try {
      await services.parts.remove(part.id);
      toast.success("Part deleted");
      onChanged();
    } catch (e) {
      toast.error(errorMessage(e, "Delete failed"));
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.04, 0.35), duration: 0.3 }}
      className="glass group overflow-hidden rounded-2xl transition-shadow hover:shadow-[0_0_36px_-14px_hsl(258_90%_66%/0.4)]"
    >
      <div
        className="relative aspect-video cursor-pointer overflow-hidden bg-black/40"
        onClick={() => part.status === "ready" && setPreview(true)}
      >
        {part.thumbnail_path ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={mediaUrl(part.thumbnail_path)}
            alt={part.label}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2">
            {busy ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin text-violet-300" />
                <span className="text-xs text-muted-foreground">
                  {part.status === "rendering" ? "Rendering…" : "Queued"}
                </span>
              </>
            ) : (
              <AlertTriangle className="h-5 w-5 text-red-400" />
            )}
          </div>
        )}

        {part.status === "ready" && (
          <div className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-white/90 shadow-xl">
              <Play className="ml-0.5 h-4 w-4 text-black" fill="currentColor" />
            </div>
          </div>
        )}

        <span className="absolute bottom-2 right-2 rounded-md bg-black/70 px-1.5 py-0.5 text-[11px] tabular-nums backdrop-blur">
          {formatDuration(part.duration)}
        </span>
        <span className="absolute left-2 top-2 rounded-md bg-black/70 px-1.5 py-0.5 text-[11px] font-medium backdrop-blur">
          #{part.index}
        </span>

        {part.viral_tier && (
          <span
            className={cn(
              "absolute right-2 top-2 flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold backdrop-blur",
              scoreTone(part.viral_score),
            )}
            title={`Viral potential ${Math.round(part.viral_score)}/100`}
          >
            <Flame className="h-3 w-3" />
            {Math.round(part.viral_score)}
          </span>
        )}
      </div>

      <div className="space-y-2 p-3">
        {editing ? (
          <div className="flex gap-1.5">
            <Input
              value={draft}
              autoFocus
              className="h-8"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") saveLabel();
                if (e.key === "Escape") {
                  setDraft(part.label);
                  setEditing(false);
                }
              }}
            />
            <Button size="icon" className="h-8 w-8 shrink-0" onClick={saveLabel} disabled={saving}>
              {saving ? <Loader2 className="animate-spin" /> : <Check />}
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 shrink-0"
              onClick={() => {
                setDraft(part.label);
                setEditing(false);
              }}
            >
              <X />
            </Button>
          </div>
        ) : (
          <button
            onClick={() => {
              setDraft(part.label);
              setEditing(true);
            }}
            disabled={busy}
            className="w-full truncate rounded-lg px-1 py-0.5 text-left text-sm font-medium transition-colors hover:bg-white/[0.06] disabled:opacity-60"
            title="Click to change the text shown on the video"
          >
            {part.label || <span className="text-muted-foreground">No text</span>}
          </button>
        )}

        {part.title && (
          <p className="truncate px-1 text-xs text-violet-300/90" title={part.title}>
            {part.title}
          </p>
        )}

        {part.viral_reason && (
          <p
            className="line-clamp-2 px-1 text-[11px] leading-snug text-muted-foreground"
            title={`${TIER_LABEL[part.viral_tier] ?? ""} — ${part.viral_reason}`}
          >
            {part.viral_reason}
          </p>
        )}

        <div className="flex items-center justify-between px-1">
          <span className="text-[11px] text-muted-foreground">
            {formatDuration(part.start_time)}–{formatDuration(part.end_time)}
            {part.size_bytes > 0 && ` · ${formatBytes(part.size_bytes)}`}
          </span>
          <div className="flex items-center gap-0.5">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              asChild
              disabled={part.status !== "ready"}
            >
              <a href={partDownloadUrl(part.id)} download title="Download">
                <Download />
              </a>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-red-400 hover:text-red-300"
              onClick={remove}
              title="Delete"
            >
              <Trash2 />
            </Button>
          </div>
        </div>

        {part.export_status !== "none" && (
          <p
            className="flex items-center gap-1.5 px-1 text-[11px]"
            title={part.export_target || part.export_error}
          >
            {part.export_status === "saving" && (
              <>
                <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                <span className="text-muted-foreground">Saving…</span>
              </>
            )}
            {part.export_status === "saved" && (
              <>
                {part.export_target.startsWith("http") ? (
                  <CloudUpload className="h-3 w-3 text-emerald-400" />
                ) : (
                  <FolderOpen className="h-3 w-3 text-emerald-400" />
                )}
                <span className="truncate text-emerald-400/90">Saved</span>
              </>
            )}
            {part.export_status === "error" && (
              <>
                <AlertTriangle className="h-3 w-3 shrink-0 text-red-400" />
                <span className="truncate text-red-400/90">{part.export_error}</span>
              </>
            )}
          </p>
        )}
      </div>

      <Dialog open={preview} onOpenChange={setPreview}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{part.label || `Part ${part.index}`}</DialogTitle>
            <DialogDescription>
              {formatDuration(part.start_time)} – {formatDuration(part.end_time)} of the source video
            </DialogDescription>
          </DialogHeader>
          {preview && part.path && (
            <video
              src={mediaUrl(part.path)}
              controls
              autoPlay
              className="aspect-video w-full rounded-xl bg-black"
              poster={part.thumbnail_path ? mediaUrl(part.thumbnail_path) : undefined}
            />
          )}

          {part.viral_tier && (
            <div className="rounded-xl border border-primary/20 bg-primary/[0.06] p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-xs font-medium text-violet-300">
                  <Sparkles className="h-3.5 w-3.5" />
                  {TIER_LABEL[part.viral_tier] ?? "Rating"}
                </span>
                <span
                  className={cn(
                    "rounded-md px-2 py-0.5 text-xs font-semibold",
                    scoreTone(part.viral_score),
                  )}
                >
                  {Math.round(part.viral_score)}/100
                </span>
              </div>
              <p className="text-xs leading-relaxed text-foreground/90">{part.viral_reason}</p>
              {part.viral_hook > 0 && (
                <div className="mt-2">
                  <div className="mb-1 flex justify-between text-[11px] text-muted-foreground">
                    <span>Hook strength</span>
                    <span className="tabular-nums">{Math.round(part.viral_hook)}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.08]">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500"
                      style={{ width: `${Math.min(part.viral_hook, 100)}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}
          {part.transcript && (
            <div className="max-h-24 overflow-y-auto rounded-xl bg-white/[0.03] p-3 text-xs leading-relaxed text-muted-foreground">
              {part.transcript}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}

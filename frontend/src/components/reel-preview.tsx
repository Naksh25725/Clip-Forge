"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Overlay, Video } from "@/types";

// Must match the backend's drawtext sizing: fontsize = frame_height / factor.
const SIZE_FACTORS = { small: 16, medium: 11, large: 8 } as const;

/**
 * Live preview of a part: the actual video frame (already transformed to the
 * chosen aspect by the backend) with the text overlays on top. Drag a text
 * vertically to position it — `y` maps 1:1 onto ffmpeg's drawtext position.
 */
export function ReelPreview({
  video,
  aspect,
  reelFill,
  overlays,
  onOverlaysChange,
  sampleTotal,
  selected,
  onSelect,
  showSubtitle = false,
  subtitleY = 0.9,
  onSubtitleYChange,
  disabled,
}: {
  video: Video | null;
  aspect: "source" | "reel";
  reelFill: "crop" | "fit";
  overlays: Overlay[];
  onOverlaysChange: (next: Overlay[]) => void;
  sampleTotal: number;
  selected: number;
  onSelect: (index: number) => void;
  showSubtitle?: boolean;
  subtitleY?: number;
  onSubtitleYChange?: (y: number) => void;
  disabled?: boolean;
}) {
  const ready = video?.status === "ready";
  const [time, setTime] = useState(1);
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [boxH, setBoxH] = useState(320);
  const dragIdx = useRef<number | null>(null);
  const draggingSub = useRef(false);

  // Reset the scrub position when the source video changes.
  useEffect(() => {
    setTime(video ? Math.min(1, video.duration / 2) : 1);
    setImgUrl(null);
  }, [video?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch the transformed frame (debounced while scrubbing).
  useEffect(() => {
    if (!ready || !video) return;
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_URL}/api/videos/${video.id}/preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ time, aspect, reel_fill: reelFill }),
        });
        if (!res.ok) throw new Error(String(res.status));
        const blob = await res.blob();
        setImgUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return URL.createObjectURL(blob);
        });
      } catch {
        setImgUrl(null);
      } finally {
        setLoading(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [ready, video, time, aspect, reelFill]);

  // Track rendered height so text sizes match the burn-in proportionally.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setBoxH(el.clientHeight));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const ratio =
    aspect === "reel" ? 9 / 16 : video && video.width && video.height ? video.width / video.height : 16 / 9;

  const pointerY = (e: React.PointerEvent) => {
    const rect = containerRef.current!.getBoundingClientRect();
    return Math.max(0, Math.min((e.clientY - rect.top) / rect.height, 1));
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!containerRef.current) return;
    if (draggingSub.current) {
      const y = Math.min(Math.max(pointerY(e), 0.2), 0.98);
      onSubtitleYChange?.(Math.round(y * 100) / 100);
      return;
    }
    if (dragIdx.current === null) return;
    const y = Math.round(pointerY(e) * 100) / 100;
    const idx = dragIdx.current;
    onOverlaysChange(overlays.map((o, i) => (i === idx ? { ...o, y } : o)));
  };

  const endDrag = () => {
    dragIdx.current = null;
    draggingSub.current = false;
  };

  const sample = (text: string) =>
    text.replace(/\{n\}/g, "1").replace(/\{total\}/g, String(Math.max(sampleTotal, 1)));

  return (
    <div className="space-y-2">
      <div
        ref={containerRef}
        className="relative mx-auto select-none overflow-hidden rounded-xl border border-white/[0.08] bg-black"
        style={{ aspectRatio: `${ratio}`, maxHeight: 380, width: "auto", maxWidth: "100%" }}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        {imgUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imgUrl} alt="" className="h-full w-full object-cover" draggable={false} />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-violet-500/10 via-zinc-900 to-fuchsia-500/10">
            {ready && loading ? (
              <Loader2 className="h-5 w-5 animate-spin text-violet-300" />
            ) : (
              <span className="px-4 text-center text-xs text-muted-foreground">
                {ready ? "Loading preview…" : "Upload a video to preview"}
              </span>
            )}
          </div>
        )}

        {loading && imgUrl && (
          <div className="absolute right-2 top-2">
            <Loader2 className="h-4 w-4 animate-spin text-white/70" />
          </div>
        )}

        {overlays.map((overlay, i) => {
          const fontSize = Math.max(boxH / SIZE_FACTORS[overlay.size], 9);
          return (
            <div
              key={i}
              onPointerDown={(e) => {
                if (disabled) return;
                dragIdx.current = i;
                onSelect(i);
                (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
                e.preventDefault();
              }}
              className={cn(
                "absolute left-1/2 max-w-[94%] cursor-grab whitespace-nowrap rounded-sm px-[0.35em] py-[0.12em] font-bold leading-tight text-white active:cursor-grabbing",
                "bg-black/45 [text-shadow:2px_2px_2px_rgba(0,0,0,0.6)]",
                selected === i && "ring-2 ring-violet-400",
              )}
              style={{
                top: `${overlay.y * 100}%`,
                transform: `translate(-50%, -${overlay.y * 100}%)`,
                fontSize,
              }}
              title="Drag to position"
            >
              {sample(overlay.text) || "…"}
            </div>
          );
        })}

        {showSubtitle && (
          <div
            onPointerDown={(e) => {
              if (disabled) return;
              draggingSub.current = true;
              (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
              e.preventDefault();
            }}
            className="absolute left-1/2 flex max-w-[92%] -translate-x-1/2 cursor-grab justify-center text-center font-bold leading-tight text-white active:cursor-grabbing [text-shadow:1.5px_1.5px_2px_rgba(0,0,0,0.9)]"
            style={{ bottom: `${(1 - subtitleY) * 100}%`, fontSize: Math.max(boxH / 20, 9) }}
            title="Drag to move subtitles"
          >
            Subtitles appear here
          </div>
        )}
      </div>

      {ready && video && (
        <div className="mx-auto flex max-w-[380px] items-center gap-2 px-1">
          <input
            type="range"
            min={0}
            max={Math.max(video.duration - 0.2, 0.2)}
            step={0.5}
            value={time}
            onChange={(e) => setTime(Number(e.target.value))}
            className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-white/[0.1] accent-violet-400"
          />
          <span className="w-12 shrink-0 text-right text-[11px] tabular-nums text-muted-foreground">
            {formatDuration(time)}
          </span>
        </div>
      )}
      <p className="text-center text-[11px] text-muted-foreground/70">
        Drag the text on the preview to position it · scrub to any moment
      </p>
    </div>
  );
}

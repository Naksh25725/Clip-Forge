"use client";

import {
  Captions,
  Flame,
  Plus,
  RectangleHorizontal,
  Smartphone,
  Sparkles,
  Trash2,
  Type,
} from "lucide-react";
import { useState } from "react";
import { ReelPreview } from "@/components/reel-preview";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AiStatus, Overlay, SplitOptions, Video } from "@/types";

export const DEFAULT_OPTIONS: SplitOptions = {
  mode: "count",
  count: 4,
  duration_seconds: 60,
  best_count: 5,
  clip_length: 45,
  aspect: "source",
  reel_fill: "crop",
  overlays: [{ text: "Part {n}", y: 0.85, size: "medium" }],
  quality: "high",
  resolution: "source",
  format: "mp4",
  ai_titles: false,
  subtitles: false,
  subtitle_y: 0.9,
  transcription: "auto",
  output_mode: "local",
  output_dir: "",
  drive_folder_id: "root",
};

/** Mirrors the backend's segment planner so the preview text stays honest. */
export function previewParts(duration: number, options: SplitOptions): number {
  if (!duration) return 0;
  if (options.mode === "best") {
    // Can't exceed how many non-overlapping clips actually fit.
    const fits = Math.max(
      1,
      Math.floor(duration / Math.max(options.clip_length, 5)),
    );
    return Math.min(options.best_count, fits);
  }
  if (options.mode === "count")
    return Math.max(1, Math.min(options.count, 200));
  const step = Math.max(options.duration_seconds, 1);
  let n = Math.ceil(duration / step);
  // The planner folds a final sliver shorter than 0.5s into the previous part.
  if (n > 1 && duration - (n - 1) * step < 0.5) n -= 1;
  return Math.max(n, 1);
}

function TranscriptionAndAISection({
  options,
  disabled,
  aiStatus,
  set,
}: {
  options: SplitOptions;
  disabled?: boolean;
  aiStatus?: AiStatus;
  set: <K extends keyof SplitOptions>(key: K, value: SplitOptions[K]) => void;
}) {
  return (
    <>
      {/* Transcription engine — matters for best-clips and AI names */}
      {(options.mode === "best" || options.ai_titles || options.subtitles) &&
        (aiStatus?.cloud_stt_available || aiStatus?.whisper_available) && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white/[0.03] p-4">
            <div>
              <Label>Transcription</Label>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {options.transcription === "local"
                  ? "Runs on this device — private, but slow on long videos."
                  : "Groq cloud is ~100× faster and more accurate; falls back to this device if the cloud is unavailable."}
              </p>
            </div>
            <Select
              value={options.transcription}
              disabled={disabled}
              onValueChange={(v) =>
                set("transcription", v as SplitOptions["transcription"])
              }
            >
              <SelectTrigger className="w-52">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {aiStatus?.cloud_stt_available && (
                  <SelectItem value="auto">Fast cloud (Groq)</SelectItem>
                )}
                {aiStatus?.whisper_available && (
                  <SelectItem value="local">On this device</SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>
        )}

      {/* AI: automatic in best-clips mode, opt-in otherwise */}
      {options.mode === "best" ? (
        <div className="rounded-xl bg-white/[0.03] p-4">
          <div className="flex gap-2">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-violet-300" />
            <div className="text-xs">
              <Label className="text-sm">How clips get rated</Label>
              {aiStatus?.has_key && aiStatus?.whisper_available ? (
                <p className="mt-0.5 text-muted-foreground">
                  Groq{" "}
                  <span className="text-violet-300">({aiStatus.model})</span>{" "}
                  reads the transcript and scores each moment on hook strength,
                  payoff and emotional charge — blended with audio energy and
                  on-screen activity.
                </p>
              ) : aiStatus?.whisper_available ? (
                <p className="mt-0.5 text-muted-foreground">
                  Scored on transcript signals (hook phrases, emotive words,
                  speaking pace) plus audio energy and scene changes.{" "}
                  <span className="text-amber-300/90">
                    Add a free GROQ_API_KEY for AI ratings with written
                    reasoning.
                  </span>
                </p>
              ) : (
                <p className="mt-0.5 text-muted-foreground">
                  Scored on audio energy and on-screen activity.{" "}
                  <span className="text-amber-300/90">
                    Install faster-whisper and add a GROQ_API_KEY for AI ratings
                    that understand what’s actually said.
                  </span>
                </p>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-4 rounded-xl bg-white/[0.03] p-4">
          <div className="flex gap-2">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-violet-300" />
            <div>
              <Label>AI part names</Label>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Transcribes the audio and names each part with Groq{" "}
                {aiStatus?.model && (
                  <span className="text-violet-300">({aiStatus.model})</span>
                )}
                . Used for the saved filenames.
              </p>
              {aiStatus && !aiStatus.has_key && (
                <p className="mt-1 text-xs text-amber-300/90">
                  Add a free GROQ_API_KEY to your .env to enable this.
                </p>
              )}
              {aiStatus?.has_key && !aiStatus.whisper_available && (
                <p className="mt-1 text-xs text-amber-300/90">
                  Needs faster-whisper — run: pip install faster-whisper
                </p>
              )}
            </div>
          </div>
          <Switch
            checked={options.ai_titles}
            disabled={
              disabled || !aiStatus?.has_key || !aiStatus?.whisper_available
            }
            onCheckedChange={(v) => set("ai_titles", v)}
          />
        </div>
      )}
    </>
  );
}

function OutputEncodingSection({
  options,
  disabled,
  set,
}: {
  options: SplitOptions;
  disabled?: boolean;
  set: <K extends keyof SplitOptions>(key: K, value: SplitOptions[K]) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <div>
        <Label className="mb-1.5 block text-xs">Quality</Label>
        <Select
          value={options.quality}
          disabled={disabled}
          onValueChange={(v) => set("quality", v as SplitOptions["quality"])}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="best">Best</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="mb-1.5 block text-xs">Resolution</Label>
        <Select
          value={options.resolution}
          disabled={disabled}
          onValueChange={(v) =>
            set("resolution", v as SplitOptions["resolution"])
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="source">Same as source</SelectItem>
            <SelectItem value="1080">1080p</SelectItem>
            <SelectItem value="720">720p</SelectItem>
            <SelectItem value="480">480p</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="mb-1.5 block text-xs">Format</Label>
        <Select
          value={options.format}
          disabled={disabled}
          onValueChange={(v) => set("format", v as SplitOptions["format"])}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="mp4">MP4</SelectItem>
            <SelectItem value="mov">MOV</SelectItem>
            <SelectItem value="webm">WEBM</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}

function TextAndPreviewSection({
  options,
  disabled,
  video,
  aiStatus,
  count,
  selectedOverlay,
  setSelectedOverlay,
  set,
}: {
  options: SplitOptions;
  disabled?: boolean;
  video: Video | null;
  aiStatus?: AiStatus;
  count: number;
  selectedOverlay: number;
  setSelectedOverlay: (index: number) => void;
  set: <K extends keyof SplitOptions>(key: K, value: SplitOptions[K]) => void;
}) {
  return (
    <div className="rounded-xl bg-white/[0.03] p-4">
      <div className="mb-3 flex items-center gap-2">
        <Type className="h-4 w-4 text-violet-300" />
        <Label>Text on each part</Label>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_240px]">
        <div className="space-y-2">
          {options.overlays.map((overlay, i) => (
            <div
              key={i}
              className={cn(
                "flex items-center gap-2 rounded-lg border p-1.5 transition-colors",
                selectedOverlay === i
                  ? "border-violet-400/40 bg-white/[0.03]"
                  : "border-transparent",
              )}
              onClick={() => setSelectedOverlay(i)}
            >
              <Input
                value={overlay.text}
                disabled={disabled}
                placeholder="Text…"
                className="h-8"
                onChange={(e) =>
                  set(
                    "overlays",
                    options.overlays.map((o, j) =>
                      j === i ? { ...o, text: e.target.value } : o,
                    ),
                  )
                }
              />
              <Select
                value={overlay.size}
                disabled={disabled}
                onValueChange={(v) =>
                  set(
                    "overlays",
                    options.overlays.map((o, j) =>
                      j === i ? { ...o, size: v as Overlay["size"] } : o,
                    ),
                  )
                }
              >
                <SelectTrigger className="h-8 w-24 shrink-0">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="small">Small</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="large">Large</SelectItem>
                </SelectContent>
              </Select>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0 text-red-400/80 hover:text-red-300"
                disabled={disabled}
                onClick={(e) => {
                  e.stopPropagation();
                  set(
                    "overlays",
                    options.overlays.filter((_, j) => j !== i),
                  );
                  setSelectedOverlay(0);
                }}
                title="Remove this text"
              >
                <Trash2 />
              </Button>
            </div>
          ))}

          {options.overlays.length < 6 && (
            <Button
              variant="outline"
              size="sm"
              disabled={disabled}
              onClick={() => {
                set("overlays", [
                  ...options.overlays,
                  { text: "", y: 0.5, size: "medium" },
                ]);
                setSelectedOverlay(options.overlays.length);
              }}
            >
              <Plus /> Add text
            </Button>
          )}
          {options.overlays.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No text — clips render clean with nothing burned in.
            </p>
          )}
          {options.mode !== "best" && (
            <p className="text-xs text-muted-foreground">
              <code className="text-violet-300">{"{n}"}</code> = part number,{" "}
              <code className="text-violet-300">{"{total}"}</code> = total
              parts. Each part can still be edited after generating.
            </p>
          )}
        </div>

        <ReelPreview
          video={video}
          aspect={options.aspect}
          reelFill={options.reel_fill}
          overlays={options.overlays}
          onOverlaysChange={(next) => set("overlays", next)}
          sampleTotal={count || 1}
          selected={selectedOverlay}
          onSelect={setSelectedOverlay}
          showSubtitle={options.subtitles}
          subtitleY={options.subtitle_y}
          onSubtitleYChange={(y) => set("subtitle_y", y)}
          disabled={disabled}
        />
      </div>

      <div className="mt-3 flex items-start justify-between gap-4 border-t border-white/[0.06] pt-3">
        <div className="flex gap-2">
          <Captions className="mt-0.5 h-4 w-4 shrink-0 text-violet-300" />
          <div>
            <Label>Subtitles</Label>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Burn the spoken words onto each clip, timed to the audio.
              {options.subtitles && (
                <span className="text-violet-300">
                  {" "}
                  Drag the caption on the preview to move it.
                </span>
              )}
              {!aiStatus?.cloud_stt_available &&
                !aiStatus?.whisper_available && (
                  <span className="text-amber-300/90">
                    {" "}
                    Needs transcription — add a GROQ_API_KEY or install
                    faster-whisper.
                  </span>
                )}
            </p>
          </div>
        </div>
        <Switch
          checked={options.subtitles}
          disabled={
            disabled ||
            (!aiStatus?.cloud_stt_available && !aiStatus?.whisper_available)
          }
          onCheckedChange={(v) => set("subtitles", v)}
        />
      </div>
    </div>
  );
}

function OutputFormatSection({
  options,
  disabled,
  set,
}: {
  options: SplitOptions;
  disabled?: boolean;
  set: <K extends keyof SplitOptions>(key: K, value: SplitOptions[K]) => void;
}) {
  return (
    <div>
      <Label className="mb-2 block">Output format</Label>
      <div className="grid gap-2 sm:grid-cols-2">
        <button
          type="button"
          disabled={disabled}
          onClick={() => set("aspect", "source")}
          className={cn(
            "flex items-center gap-2.5 rounded-xl border p-3 text-left transition-colors disabled:opacity-50",
            options.aspect === "source"
              ? "border-primary/50 bg-primary/10"
              : "border-white/[0.08] hover:bg-white/[0.04]",
          )}
        >
          <RectangleHorizontal className="h-4 w-4 shrink-0 text-violet-300" />
          <div>
            <span className="text-sm font-medium">Keep original</span>
            <p className="text-xs text-muted-foreground">
              Same shape as the source video
            </p>
          </div>
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => set("aspect", "reel")}
          className={cn(
            "flex items-center gap-2.5 rounded-xl border p-3 text-left transition-colors disabled:opacity-50",
            options.aspect === "reel"
              ? "border-primary/50 bg-primary/10"
              : "border-white/[0.08] hover:bg-white/[0.04]",
          )}
        >
          <Smartphone className="h-4 w-4 shrink-0 text-violet-300" />
          <div>
            <span className="text-sm font-medium">Reel · 9:16 vertical</span>
            <p className="text-xs text-muted-foreground">
              For Reels, Shorts and TikTok
            </p>
          </div>
        </button>
      </div>

      {options.aspect === "reel" && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <button
            type="button"
            disabled={disabled}
            onClick={() => set("reel_fill", "crop")}
            className={cn(
              "rounded-xl border p-2.5 text-left transition-colors disabled:opacity-50",
              options.reel_fill === "crop"
                ? "border-primary/50 bg-primary/10"
                : "border-white/[0.08] hover:bg-white/[0.04]",
            )}
          >
            <span className="text-xs font-medium">Fit to screen</span>
            <p className="text-[11px] text-muted-foreground">
              Fills the whole screen — the sides get cropped off
            </p>
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => set("reel_fill", "fit")}
            className={cn(
              "rounded-xl border p-2.5 text-left transition-colors disabled:opacity-50",
              options.reel_fill === "fit"
                ? "border-primary/50 bg-primary/10"
                : "border-white/[0.08] hover:bg-white/[0.04]",
            )}
          >
            <span className="text-xs font-medium">Keep full video</span>
            <p className="text-[11px] text-muted-foreground">
              Whole frame visible, blurred background above and below
            </p>
          </button>
        </div>
      )}
    </div>
  );
}

function SplitModeSection({
  options,
  disabled,
  duration,
  count,
  each,
  withMode,
  changeMode,
}: {
  options: SplitOptions;
  disabled?: boolean;
  duration: number;
  count: number;
  each: number;
  withMode: (mode: SplitOptions["mode"], patch?: Partial<SplitOptions>) => void;
  changeMode: (mode: SplitOptions["mode"]) => void;
}) {
  return (
    <div>
      <Label className="mb-2 block">What do you want out of this video?</Label>

      <button
        type="button"
        disabled={disabled}
        onClick={() => changeMode("best")}
        className={cn(
          "mb-2 w-full rounded-xl border p-3 text-left transition-colors disabled:opacity-50",
          options.mode === "best"
            ? "border-primary/50 bg-primary/10"
            : "border-white/[0.08] hover:bg-white/[0.04]",
        )}
      >
        <div className="flex items-center gap-2">
          <Flame className="h-4 w-4 text-orange-400" />
          <span className="text-sm font-medium">Best clips only</span>
          <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[10px] font-medium text-orange-300">
            rated
          </span>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Finds the strongest moments and scores each one for viral potential
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Input
            type="number"
            min={1}
            max={30}
            value={options.best_count}
            disabled={disabled}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => {
              const v = Number(e.target.value);
              withMode("best", {
                best_count: Math.max(1, Math.min(v || 1, 30)),
              });
            }}
            className="h-8 w-20"
          />
          <span className="text-xs text-muted-foreground">
            clips, each about
          </span>
          <Input
            type="number"
            min={5}
            max={600}
            value={options.clip_length}
            disabled={disabled}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => {
              const v = Number(e.target.value);
              withMode("best", {
                clip_length: Math.max(5, Math.min(v || 5, 600)),
              });
            }}
            className="h-8 w-20"
          />
          <span className="text-xs text-muted-foreground">seconds long</span>
        </div>
      </button>

      <p className="mb-2 text-xs text-muted-foreground/70">
        Or cut up the whole video:
      </p>

      <div className="grid gap-2 sm:grid-cols-2">
        <button
          type="button"
          disabled={disabled}
          onClick={() => changeMode("count")}
          className={cn(
            "rounded-xl border p-3 text-left transition-colors disabled:opacity-50",
            options.mode === "count"
              ? "border-primary/50 bg-primary/10"
              : "border-white/[0.08] hover:bg-white/[0.04]",
          )}
        >
          <span className="text-sm font-medium">Equal parts</span>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Split into a set number
          </p>
          <div className="mt-2 flex items-center gap-2">
            <Input
              type="number"
              min={1}
              max={200}
              value={options.count}
              disabled={disabled}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => {
                const v = Number(e.target.value);
                withMode("count", {
                  count: Math.max(1, Math.min(v || 1, 200)),
                });
              }}
              className="h-8 w-20"
            />
            <span className="text-xs text-muted-foreground">parts</span>
          </div>
        </button>

        <button
          type="button"
          disabled={disabled}
          onClick={() => changeMode("duration")}
          className={cn(
            "rounded-xl border p-3 text-left transition-colors disabled:opacity-50",
            options.mode === "duration"
              ? "border-primary/50 bg-primary/10"
              : "border-white/[0.08] hover:bg-white/[0.04]",
          )}
        >
          <span className="text-sm font-medium">Fixed length</span>
          <p className="mt-0.5 text-xs text-muted-foreground">
            A new part every N seconds
          </p>
          <div className="mt-2 flex items-center gap-2">
            <Input
              type="number"
              min={3}
              max={7200}
              value={options.duration_seconds}
              disabled={disabled}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => {
                const v = Number(e.target.value);
                withMode("duration", {
                  duration_seconds: Math.max(3, Math.min(v || 3, 7200)),
                });
              }}
              className="h-8 w-20"
            />
            <span className="text-xs text-muted-foreground">seconds</span>
          </div>
        </button>
      </div>
      {duration > 0 && (
        <p className="mt-2 text-xs text-violet-300">
          {options.mode === "best" ? (
            <>
              → the top {count} moment{count === 1 ? "" : "s"} out of{" "}
              {formatDuration(duration)}
              {count < options.best_count && " (all that fit at this length)"}
            </>
          ) : (
            <>
              → {count} part{count === 1 ? "" : "s"}
              {each > 0 && `, about ${formatDuration(each)} each`}
            </>
          )}
        </p>
      )}
    </div>
  );
}

export function SplitPanel({
  options,
  onChange,
  duration,
  video,
  aiStatus,
  disabled,
}: {
  options: SplitOptions;
  onChange: (next: SplitOptions) => void;
  duration: number;
  video: Video | null;
  aiStatus?: AiStatus;
  disabled?: boolean;
}) {
  const set = <K extends keyof SplitOptions>(key: K, value: SplitOptions[K]) =>
    onChange({ ...options, [key]: value });
  const [selectedOverlay, setSelectedOverlay] = useState(0);

  // "Part {n}" branding belongs to the split-everything modes. Best clips are
  // standalone, so entering that mode drops the numbered label (custom texts
  // stay), and leaving it brings the default back if no text is left.
  const withMode = (
    mode: SplitOptions["mode"],
    patch: Partial<SplitOptions> = {},
  ) => {
    let overlays = options.overlays;
    if (mode === "best") {
      overlays = overlays.filter((o) => !o.text.includes("{n}"));
    } else if (overlays.length === 0) {
      overlays = [{ text: "Part {n}", y: 0.85, size: "medium" }];
    }
    onChange({ ...options, ...patch, mode, overlays });
    setSelectedOverlay(0);
  };
  const changeMode = (mode: SplitOptions["mode"]) => withMode(mode);

  const count = previewParts(duration, options);
  const each = duration && count ? duration / count : 0;

  return (
    <div className="space-y-5">
      <SplitModeSection
        options={options}
        disabled={disabled}
        duration={duration}
        count={count}
        each={each}
        withMode={withMode}
        changeMode={changeMode}
      />

      <OutputFormatSection options={options} disabled={disabled} set={set} />

      <TextAndPreviewSection
        options={options}
        disabled={disabled}
        video={video}
        aiStatus={aiStatus}
        count={count}
        selectedOverlay={selectedOverlay}
        setSelectedOverlay={setSelectedOverlay}
        set={set}
      />

      <OutputEncodingSection options={options} disabled={disabled} set={set} />

      <TranscriptionAndAISection
        options={options}
        disabled={disabled}
        aiStatus={aiStatus}
        set={set}
      />
    </div>
  );
}

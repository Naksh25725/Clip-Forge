"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Ban,
  Clapperboard,
  CloudUpload,
  Download,
  Flame,
  FolderOpen,
  Loader2,
  Scissors,
  Sparkles,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";
import { OutputPanel } from "@/components/output-panel";
import { PartCard } from "@/components/part-card";
import { SourcePanel } from "@/components/source-panel";
import { DEFAULT_OPTIONS, SplitPanel, previewParts } from "@/components/split-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { errorMessage, fetcher } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";
import * as services from "@/services";
import type { AiStatus, DriveStatus, JobDetail, SplitOptions, Video } from "@/types";

function Section({
  step,
  title,
  children,
  className,
}: {
  step: number;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("glass rounded-2xl p-5", className)}>
      <div className="mb-4 flex items-center gap-2.5">
        <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-primary/15 text-xs font-semibold text-violet-300">
          {step}
        </span>
        <h2 className="font-semibold">{title}</h2>
      </div>
      {children}
    </section>
  );
}

/** Elapsed + time-left estimate from a sliding window of progress samples. */
function useJobTiming(job: JobDetail | undefined) {
  const samplesRef = useRef<{ id: string; samples: [number, number][] }>({ id: "", samples: [] });
  const [text, setText] = useState("");

  useEffect(() => {
    if (!job || (job.status !== "running" && job.status !== "queued")) {
      setText("");
      return;
    }
    const store = samplesRef.current;
    if (store.id !== job.id) {
      store.id = job.id;
      store.samples = [];
    }
    const now = Date.now();
    store.samples.push([now, job.progress]);
    store.samples = store.samples.filter(([t]) => now - t < 90_000);

    const elapsed = job.started_at
      ? Math.max((now - new Date(job.started_at).getTime()) / 1000, 0)
      : 0;
    let eta = "";
    if (store.samples.length >= 2) {
      const [t0, p0] = store.samples[0];
      const [t1, p1] = store.samples[store.samples.length - 1];
      const dt = (t1 - t0) / 1000;
      const dp = p1 - p0;
      if (dt > 8 && dp > 0.3) {
        eta = ` · ~${formatDuration(((100 - job.progress) / dp) * dt)} left`;
      }
    }
    setText(elapsed > 1 ? `${formatDuration(elapsed)} elapsed${eta}` : "");
  }, [job]);

  return text;
}

function Dashboard() {
  const searchParams = useSearchParams();
  const [video, setVideo] = useState<Video | null>(null);
  const [options, setOptions] = useState<SplitOptions>(DEFAULT_OPTIONS);
  const [jobId, setJobId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const settingsLoaded = useRef(false);

  const { data: aiStatus } = useSWR<AiStatus>("/api/ai/status", fetcher);
  const { data: driveStatus, mutate: refreshDrive } = useSWR<DriveStatus>(
    "/api/drive/status",
    fetcher,
  );

  // Seed the form from saved settings once.
  useEffect(() => {
    if (settingsLoaded.current) return;
    settingsLoaded.current = true;
    services.settings
      .get()
      .then((s) =>
        setOptions((prev) => ({
          ...prev,
          overlays: s.label_template
            ? [{ text: s.label_template, y: s.label_y ?? 0.85, size: s.label_size }]
            : prev.overlays,
          aspect: s.aspect,
          reel_fill: s.reel_fill,
          subtitles: s.subtitles,
          subtitle_y: s.subtitle_y ?? 0.9,
          transcription: s.transcription_mode,
          quality: s.quality,
          resolution: s.resolution,
          format: s.format,
          output_mode: s.output_mode,
          output_dir: s.output_dir,
          drive_folder_id: s.drive_folder_id,
        })),
      )
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const drive = searchParams.get("drive");
    if (drive === "connected") {
      toast.success("Google Drive connected");
      refreshDrive();
    } else if (drive === "error") {
      toast.error("Google Drive connection failed");
    }
    if (drive) window.history.replaceState({}, "", "/");
  }, [searchParams, refreshDrive]);

  // Poll the source video while a link download is in flight.
  const downloading = video?.status === "downloading";
  const { data: polledVideo } = useSWR<Video>(
    downloading ? `/api/videos/${video!.id}` : null,
    fetcher,
    { refreshInterval: 1200 },
  );
  useEffect(() => {
    if (!polledVideo) return;
    setVideo(polledVideo);
    if (polledVideo.status === "ready") toast.success("Download complete");
    if (polledVideo.status === "error") toast.error(polledVideo.error || "Download failed");
  }, [polledVideo]);

  // Poll the running job.
  const { data: job, mutate: refreshJob } = useSWR<JobDetail>(
    jobId ? `/api/jobs/${jobId}` : null,
    fetcher,
    {
      refreshInterval: (latest) =>
        latest && (latest.status === "running" || latest.status === "queued") ? 1500 : 0,
    },
  );

  const running = job?.status === "running" || job?.status === "queued";
  const timing = useJobTiming(job);
  const parts = job?.parts ?? [];
  const readyParts = parts.filter((p) => p.status === "ready");
  const expectedParts = previewParts(video?.duration ?? 0, options);
  const bestMode = options.mode === "best";
  const ratedRun = parts.some((p) => p.viral_tier);

  const jobDoneRef = useRef<string | null>(null);
  useEffect(() => {
    if (job?.status === "done" && jobDoneRef.current !== job.id) {
      jobDoneRef.current = job.id;
      toast.success(`${job.parts.length} parts ready`);
    }
    if (job?.status === "error" && jobDoneRef.current !== job.id) {
      jobDoneRef.current = job.id;
      toast.error(job.error || "Processing failed");
    }
  }, [job]);

  const generate = async () => {
    if (!video) return;
    setStarting(true);
    try {
      // Remember these choices for next time.
      const first = options.overlays[0];
      services.settings
        .update({
          label_template: first?.text ?? "",
          label_y: first?.y ?? 0.85,
          label_size: first?.size ?? "medium",
          aspect: options.aspect,
          reel_fill: options.reel_fill,
          subtitles: options.subtitles,
          subtitle_y: options.subtitle_y,
          transcription_mode: options.transcription,
          quality: options.quality,
          resolution: options.resolution,
          format: options.format,
          output_mode: options.output_mode,
          output_dir: options.output_dir,
          drive_folder_id: options.drive_folder_id,
        })
        .catch(() => undefined);

      const created = await services.jobs.create(video.id, options);
      setJobId(created.id);
      jobDoneRef.current = null;
      toast.info("Generating parts…");
    } catch (e) {
      toast.error(errorMessage(e, "Could not start"));
    } finally {
      setStarting(false);
    }
  };

  const cancel = async () => {
    if (!jobId) return;
    try {
      await services.jobs.cancel(jobId);
      toast.info("Stopping after the current part");
      refreshJob();
    } catch (e) {
      toast.error(errorMessage(e, "Cancel failed"));
    }
  };

  const saveAll = async () => {
    if (!readyParts.length) return;
    if (options.output_mode === "none") {
      toast.error("Pick a destination in step 3 first");
      return;
    }
    setExporting(true);
    try {
      const mode = options.output_mode as "local" | "drive";
      const destination = mode === "drive" ? options.drive_folder_id : options.output_dir;
      const { started } = await services.parts.export(
        readyParts.map((p) => p.id),
        mode,
        destination,
      );
      toast.success(`Saving ${started} part${started === 1 ? "" : "s"}…`);
      setTimeout(() => refreshJob(), 1500);
    } catch (e) {
      toast.error(errorMessage(e, "Export failed"));
    } finally {
      setExporting(false);
    }
  };

  const reset = useCallback(() => {
    setVideo(null);
    setJobId(null);
  }, []);

  const canGenerate = video?.status === "ready" && !running && !starting;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-white/[0.06] bg-background/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
          <div className="flex items-center gap-2.5">
            <div className="glow flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-600">
              <Clapperboard className="h-4 w-4 text-white" />
            </div>
            <div>
              <span className="text-lg font-semibold tracking-tight">
                Clip<span className="text-gradient">Forge</span>
              </span>
              <p className="-mt-1 text-[11px] text-muted-foreground">Split any video into parts</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {aiStatus?.has_key && (
              <Badge variant="secondary" className="gap-1">
                <Sparkles className="h-3 w-3" /> Groq
              </Badge>
            )}
            {driveStatus?.connected && (
              <Badge variant="secondary" className="gap-1">
                <CloudUpload className="h-3 w-3" /> Drive
              </Badge>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-4 px-6 py-8">
        <Section step={1} title="Pick your video">
          <SourcePanel
            video={video}
            onVideo={setVideo}
            onClear={reset}
            disabled={running || starting}
          />
        </Section>

        <Section step={2} title="Split into parts">
          <SplitPanel
            options={options}
            onChange={setOptions}
            duration={video?.duration ?? 0}
            video={video}
            aiStatus={aiStatus}
            disabled={running || starting}
          />
        </Section>

        <Section step={3} title="Where should parts be saved?">
          <OutputPanel
            options={options}
            onChange={setOptions}
            driveStatus={driveStatus}
            onDriveChanged={refreshDrive}
            disabled={running || starting}
          />
        </Section>

        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Button size="lg" onClick={generate} disabled={!canGenerate} className="flex-1 sm:flex-none">
            {starting ? (
              <Loader2 className="animate-spin" />
            ) : bestMode ? (
              <Flame />
            ) : (
              <Scissors />
            )}
            {bestMode ? "Find best clips" : "Generate all parts"}
            {video?.status === "ready" && expectedParts > 0 && ` (${expectedParts})`}
          </Button>
          {running && (
            <Button size="lg" variant="outline" onClick={cancel}>
              <Ban /> Stop
            </Button>
          )}
          {!video && (
            <span className="text-sm text-muted-foreground">Add a video to get started.</span>
          )}
          {video?.status === "downloading" && (
            <span className="text-sm text-muted-foreground">Waiting for the download to finish…</span>
          )}
        </div>

        <AnimatePresence>
          {running && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="glass flex items-center gap-4 rounded-2xl p-5"
            >
              <Loader2 className="h-5 w-5 shrink-0 animate-spin text-violet-300" />
              <div className="flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <p className="text-sm font-medium">{job?.message || "Starting…"}</p>
                  {timing && (
                    <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                      {timing}
                    </span>
                  )}
                </div>
                <Progress value={job?.progress ?? 0} className="mt-2" />
              </div>
              <span className="shrink-0 text-sm tabular-nums text-muted-foreground">
                {Math.round(job?.progress ?? 0)}%
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        {parts.length > 0 && (
          <div className="pt-4">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-semibold">
                {ratedRun ? "Best clips" : "Parts"}{" "}
                <span className="text-sm font-normal text-muted-foreground">
                  ({readyParts.length}/{parts.length} ready)
                </span>
              </h2>
              {readyParts.length > 0 && options.output_mode !== "none" && (
                <Button variant="outline" onClick={saveAll} disabled={exporting}>
                  {exporting ? (
                    <Loader2 className="animate-spin" />
                  ) : options.output_mode === "drive" ? (
                    <CloudUpload />
                  ) : (
                    <FolderOpen />
                  )}
                  Save all to {options.output_mode === "drive" ? "Drive" : "folder"}
                </Button>
              )}
            </div>
            <p className="mb-4 -mt-2 text-xs text-muted-foreground">
              {ratedRun
                ? "Scored 0–100 for viral potential — open a clip to see the full reasoning. Click its text to change what’s shown on the video."
                : "Click a part’s text to change what’s shown on the video — it re-renders that part."}
            </p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {parts.map((part, i) => (
                <PartCard key={part.id} part={part} index={i} onChanged={() => refreshJob()} />
              ))}
            </div>
          </div>
        )}

        {!parts.length && !running && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground/70">
            <Download className="h-4 w-4" />
            Generated parts will appear here.
          </div>
        )}
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <Dashboard />
    </Suspense>
  );
}

"""Split pipeline: segment → (optional transcript + AI names) → render → export."""

import logging
import tempfile
from pathlib import Path

from ..config import get_settings
from ..database import SessionLocal
from ..models import Job, Part, Video
from ..schemas import SplitOptions
from ..services import ai, ffmpeg, subtitles, viral
from ..services.export import ExportError, export_part, safe_filename
from .queue import is_cancelled

logger = logging.getLogger(__name__)


def plan_segments(duration: float, options: SplitOptions) -> list[tuple[float, float]]:
    """Cover the whole video with non-overlapping [start, end) segments."""
    duration = max(duration, 0.1)
    if options.mode == "count":
        count = max(1, min(options.count, 200))
        step = duration / count
        bounds = [(i * step, (i + 1) * step) for i in range(count)]
    else:
        step = max(float(options.duration_seconds), 1.0)
        bounds = []
        start = 0.0
        while start < duration - 0.05:
            bounds.append((start, min(start + step, duration)))
            start += step
    # Snap the last segment to the exact end and drop sub-second slivers.
    if bounds:
        bounds[-1] = (bounds[-1][0], duration)
        if len(bounds) > 1 and bounds[-1][1] - bounds[-1][0] < 0.5:
            bounds.pop()
            bounds[-1] = (bounds[-1][0], duration)
    return bounds or [(0.0, duration)]


async def _update_job(job_id: str, progress: float, message: str) -> None:
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job:
            job.progress = round(min(progress, 99.0), 1)
            job.message = message
            await db.commit()
            # Mirror progress into the console so the engine window is watchable.
            logger.info("job %s │ %5.1f%% │ %s", job_id[:8], job.progress, message)


def _slice_transcript(segments, start: float, end: float) -> str:
    return " ".join(s.text for s in segments if s.end > start and s.start < end).strip()


async def render_one_part(part_id: str) -> None:
    """Render (or re-render) a single part from its source video."""
    settings = get_settings()
    async with SessionLocal() as db:
        part = await db.get(Part, part_id)
        if part is None:
            return
        job = await db.get(Job, part.job_id)
        video = await db.get(Video, job.video_id) if job else None
        if job is None or video is None:
            raise RuntimeError("Source video is gone")
        options = SplitOptions(**(job.options or {}))
        part.status = "rendering"
        await db.commit()
        start, end = part.start_time, part.end_time
        overlays = list(part.overlays or [])
        if not overlays and part.label:
            overlays = [{"text": part.label, "y": 0.85, "size": "medium"}]
        sub_events = list(part.subtitles or [])
        src = Path(video.path)
        source_height = video.height

    out_path = settings.parts_dir / part_id[:2] / f"{part_id}.{options.format}"
    thumb_path = settings.thumbs_dir / part_id[:2] / f"{part_id}.jpg"

    subtitle_path = None
    if sub_events and subtitles.has_subtitle_lines(sub_events):
        out_w, out_h = ffmpeg.output_dimensions(
            source_height, options.resolution, options.aspect, video.width
        )
        subtitle_path = subtitles.build_ass(
            sub_events,
            out_w,
            out_h,
            settings.parts_dir / part_id[:2] / f"{part_id}.ass",
            y=options.subtitle_y,
        )

    try:
        await ffmpeg.render_part(
            src,
            out_path,
            start,
            end,
            overlays=overlays,
            subtitle_path=subtitle_path,
            aspect=options.aspect,
            reel_fill=options.reel_fill,
            source_height=source_height,
            quality=options.quality,
            resolution=options.resolution,
            fmt=options.format,
        )
        await ffmpeg.make_thumbnail(
            out_path, thumb_path, at=min(1.0, (end - start) / 2)
        )
        async with SessionLocal() as db:
            part = await db.get(Part, part_id)
            part.path = str(out_path)
            part.thumbnail_path = str(thumb_path)
            part.size_bytes = out_path.stat().st_size if out_path.exists() else 0
            part.status = "ready"
            await db.commit()
    except ffmpeg.FFmpegError as exc:
        logger.error("Part %s render failed: %s", part_id, exc)
        async with SessionLocal() as db:
            part = await db.get(Part, part_id)
            part.status = "error"
            part.export_error = str(exc)[:500]
            await db.commit()
        raise


async def export_one_part(part_id: str, mode: str, destination: str) -> None:
    async with SessionLocal() as db:
        part = await db.get(Part, part_id)
        if part is None or part.status != "ready" or not part.path:
            return
        part.export_status = "saving"
        part.export_error = ""
        await db.commit()
        src = Path(part.path)
        base = part.title.strip() or part.label.strip() or f"part-{part.index}"
        filename = f"{part.index:02d} - {safe_filename(base)}{src.suffix}"

    try:
        location = await export_part(src, filename, mode, destination)
        async with SessionLocal() as db:
            part = await db.get(Part, part_id)
            part.export_status = "saved"
            part.export_target = location
            await db.commit()
    except (ExportError, Exception) as exc:  # noqa: BLE001
        logger.exception("Export failed for part %s", part_id)
        async with SessionLocal() as db:
            part = await db.get(Part, part_id)
            part.export_status = "error"
            part.export_error = str(exc)[:500]
            await db.commit()


async def _transcribe_source(
    src: Path,
    wav_target: Path,
    job_id: str | None = None,
    progress_from: float = 5.0,
    progress_to: float = 20.0,
    mode: str = "auto",
    duration: float = 0.0,
) -> list:
    """Extract audio and transcribe it, streaming progress into the job.

    mode: "cloud" (Groq, falls back to local), "local" (whisper on this
    machine), or "auto" (cloud when a key is present, local otherwise).
    """
    import asyncio as _asyncio

    from ..services import cloud_stt
    from ..services.transcription import transcribe, whisper_available

    if job_id:
        await _update_job(job_id, progress_from, "Preparing transcription")
    await ffmpeg.extract_audio_wav(src, wav_target)
    span = progress_to - progress_from

    use_cloud = mode == "cloud" or (mode == "auto" and cloud_stt.available())
    if use_cloud and cloud_stt.available():
        loop = _asyncio.get_running_loop()

        def cloud_progress(fraction: float, message: str) -> None:
            if job_id:
                loop.create_task(
                    _update_job(job_id, progress_from + fraction * span, message)
                )

        try:
            return await cloud_stt.transcribe(
                wav_target, duration, wav_target.parent, on_progress=cloud_progress
            )
        except cloud_stt.CloudSTTError as exc:
            logger.warning("Cloud transcription failed (%s)", exc)
            if not whisper_available():
                raise
            if job_id:
                await _update_job(
                    job_id,
                    progress_from,
                    "Cloud unavailable — transcribing on this device",
                )

    on_progress = None
    if job_id:
        loop = _asyncio.get_running_loop()

        def on_progress(fraction: float) -> None:  # called from whisper's thread
            _asyncio.run_coroutine_threadsafe(
                _update_job(
                    job_id,
                    progress_from + fraction * span,
                    f"Transcribing on this device — {fraction * 100:.0f}%",
                ),
                loop,
            )

    return await transcribe(wav_target, on_progress=on_progress)


async def _plan_best_clips(
    job_id: str, src: Path, duration: float, options: SplitOptions, workdir: Path
) -> tuple[list[viral.Candidate], list]:
    """Find the most viral-worthy moments and rate them.

    Also returns the raw transcript segments so subtitles can reuse them.
    """
    wav = workdir / "audio.wav"
    transcript_segments: list = []

    try:
        transcript_segments = await _transcribe_source(
            src,
            wav,
            job_id=job_id,
            progress_from=5,
            progress_to=18,
            mode=options.transcription,
            duration=duration,
        )
    except Exception:  # noqa: BLE001 — fall back to signal-only scoring
        logger.warning(
            "Transcription unavailable — scoring on audio/visual signal", exc_info=True
        )
        if not wav.exists():
            try:
                await ffmpeg.extract_audio_wav(src, wav)
            except ffmpeg.FFmpegError:
                logger.warning("No audio track on this video")

    await _update_job(job_id, 18, "Looking for scene changes")
    scene_times: list[float] = []
    try:
        scene_times = await ffmpeg.scene_change_times(src)
    except ffmpeg.FFmpegError:
        logger.warning("Scene detection failed; continuing without visual signal")

    candidates = viral.build_candidates(
        duration, float(options.clip_length), transcript_segments
    )
    await _update_job(
        job_id,
        24,
        f"Rating {len(candidates)} moments" + (" with AI" if ai.has_key() else ""),
    )
    scored = await viral.score_candidates(
        candidates, wav if wav.exists() else None, scene_times, use_ai=ai.has_key()
    )
    return viral.pick_best(scored, options.best_count), transcript_segments


async def run_split_job(job_id: str) -> None:
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        video = await db.get(Video, job.video_id)
        if video is None:
            raise RuntimeError("Source video no longer exists")
        options = SplitOptions(**(job.options or {}))
        src = Path(video.path)
        duration = video.duration

    if not src.exists():
        raise RuntimeError("Source file is missing from disk")

    transcript_segments: list = []
    best: list[viral.Candidate] = []

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)

        if options.mode == "best":
            best, transcript_segments = await _plan_best_clips(
                job_id, src, duration, options, workdir
            )
            if not best:
                raise RuntimeError("Could not find any usable moments in this video")
            bounds = [(c.start, c.end) for c in best]
        else:
            await _update_job(job_id, 2, "Planning parts")
            bounds = plan_segments(duration, options)

            # Transcript feeds AI names and/or subtitles.
            if options.ai_titles or options.subtitles:
                try:
                    transcript_segments = await _transcribe_source(
                        src,
                        workdir / "audio.wav",
                        job_id=job_id,
                        progress_from=4,
                        progress_to=10,
                        mode=options.transcription,
                        duration=duration,
                    )
                except Exception:  # noqa: BLE001 — optional, never fatal
                    logger.warning("Transcription unavailable", exc_info=True)

    total = len(bounds)

    async with SessionLocal() as db:
        part_ids: list[str] = []
        for i, (start, end) in enumerate(bounds, start=1):
            candidate = best[i - 1] if best else None
            resolved = options.resolve_overlays(i, total)
            part = Part(
                job_id=job_id,
                index=i,
                label=resolved[0]["text"] if resolved else "",
                overlays=resolved,
                title=candidate.title if candidate else "",
                start_time=round(start, 3),
                end_time=round(end, 3),
                duration=round(end - start, 3),
                transcript=(
                    candidate.text
                    if candidate
                    else _slice_transcript(transcript_segments, start, end)
                ),
                subtitles=(
                    subtitles.slice_segments(transcript_segments, start, end)
                    if options.subtitles
                    else []
                ),
                viral_score=round(candidate.score, 1) if candidate else 0.0,
                viral_hook=round(candidate.hook, 1) if candidate else 0.0,
                viral_reason=candidate.reason if candidate else "",
                viral_tier=candidate.tier if candidate else "",
                status="pending",
            )
            db.add(part)
            await db.flush()
            part_ids.append(part.id)
        await db.commit()

    # AI names for the non-"best" modes (best mode gets titles from the rating).
    if options.mode != "best" and options.ai_titles and transcript_segments:
        await _update_job(job_id, 10, "Naming parts with AI")
        async with SessionLocal() as db:
            parts = [await db.get(Part, pid) for pid in part_ids]
            texts = [p.transcript for p in parts]
        titles = await ai.generate_titles(texts)
        async with SessionLocal() as db:
            for pid, title in zip(part_ids, titles):
                if title:
                    part = await db.get(Part, pid)
                    part.title = title
            await db.commit()

    render_from = 30.0 if options.mode == "best" else 12.0
    noun = "clip" if options.mode == "best" else "part"
    for i, part_id in enumerate(part_ids):
        if is_cancelled(job_id):
            return
        await _update_job(
            job_id,
            render_from + (i / total) * (95 - render_from),
            f"Rendering {noun} {i + 1} of {total}",
        )
        try:
            await render_one_part(part_id)
        except ffmpeg.FFmpegError:
            continue  # part is marked errored; keep going with the rest

        if options.output_mode in ("local", "drive"):
            destination = (
                options.drive_folder_id
                if options.output_mode == "drive"
                else options.output_dir
            )
            await export_one_part(part_id, options.output_mode, destination)

    await _update_job(job_id, 99, "Wrapping up")

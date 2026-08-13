import asyncio
import logging
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import SessionLocal, get_db
from ..models import Video
from ..schemas import LinkRequest, PreviewRequest, VideoOut
from ..services import ffmpeg
from ..services.downloader import DownloadError, download

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/videos", tags=["videos"])

ALLOWED = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
CHUNK = 4 * 1024 * 1024


async def _finalize(video_id: str, path: Path, name: str) -> None:
    """Probe the file and grab a poster frame."""
    settings = get_settings()
    info = await ffmpeg.probe(path)
    thumb = settings.thumbs_dir / "sources" / f"{video_id}.jpg"
    try:
        await ffmpeg.make_thumbnail(path, thumb, at=min(1.0, info.duration / 3))
    except ffmpeg.FFmpegError:
        thumb = Path("")

    async with SessionLocal() as db:
        video = await db.get(Video, video_id)
        if video is None:
            return
        video.name = name
        video.path = str(path)
        video.size_bytes = path.stat().st_size
        video.duration = info.duration
        video.width = info.width
        video.height = info.height
        video.fps = info.fps
        video.codec = info.codec
        video.thumbnail_path = str(thumb) if thumb and thumb.exists() else ""
        video.status = "ready"
        video.progress = 100.0
        await db.commit()


@router.post("/upload", response_model=VideoOut, status_code=201)
async def upload_video(file: UploadFile, db: AsyncSession = Depends(get_db)) -> Video:
    settings = get_settings()
    name = file.filename or "video.mp4"
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(
            415, f"Unsupported format '{ext}'. Allowed: {', '.join(sorted(ALLOWED))}"
        )

    video_id = uuid.uuid4().hex
    dest = settings.uploads_dir / f"{video_id}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    try:
        async with aiofiles.open(dest, "wb") as out:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, "File exceeds the maximum upload size")
                await out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)  # don't leave partial uploads behind
        raise

    video = Video(id=video_id, name=name, source="upload", path=str(dest), status="ready")
    db.add(video)
    await db.commit()

    try:
        await _finalize(video_id, dest, name)
    except ffmpeg.FFmpegError as exc:
        await db.delete(video)
        await db.commit()
        dest.unlink(missing_ok=True)
        raise HTTPException(422, f"That file isn't a readable video: {exc}") from exc

    await db.refresh(video)
    return video


async def _download_task(video_id: str, url: str) -> None:
    settings = get_settings()

    def on_progress(pct: float) -> None:
        _progress[video_id] = pct

    try:
        path, name = await download(url, settings.uploads_dir, video_id, on_progress)
        await _finalize(video_id, path, name)
    except (DownloadError, ffmpeg.FFmpegError) as exc:
        logger.exception("Link import failed for %s", video_id)
        async with SessionLocal() as db:
            video = await db.get(Video, video_id)
            if video:
                video.status = "error"
                video.error = str(exc)[:800]
                await db.commit()
    finally:
        _progress.pop(video_id, None)


# Live download progress, keyed by video id (not worth a DB write per chunk).
_progress: dict[str, float] = {}


@router.post("/link", response_model=VideoOut, status_code=202)
async def import_from_link(payload: LinkRequest, db: AsyncSession = Depends(get_db)) -> Video:
    """Start importing a Google Drive (or direct) video link in the background."""
    video_id = uuid.uuid4().hex
    video = Video(
        id=video_id,
        name="Downloading…",
        source="link",
        source_url=payload.url.strip(),
        status="downloading",
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)

    asyncio.create_task(_download_task(video_id, payload.url.strip()))
    return video


@router.post("/{video_id}/preview")
async def preview(video_id: str, payload: PreviewRequest, db: AsyncSession = Depends(get_db)):
    """A JPEG frame with the chosen aspect transform applied (no text —
    the frontend overlays draggable text on top). Cached per parameters."""
    video = await db.get(Video, video_id)
    if not video or video.status != "ready":
        raise HTTPException(404, "Video not ready")

    settings = get_settings()
    t = max(0.0, min(payload.time, max(video.duration - 0.1, 0.0)))
    cache_key = f"{video_id}_{t:.1f}_{payload.aspect}_{payload.reel_fill}.jpg"
    cache_path = settings.thumbs_dir / "previews" / cache_key
    if not cache_path.exists():
        try:
            await ffmpeg.preview_frame(
                Path(video.path), t,
                aspect=payload.aspect, reel_fill=payload.reel_fill,
                dst=cache_path,
            )
        except ffmpeg.FFmpegError as exc:
            raise HTTPException(500, f"Preview failed: {exc}") from exc
    return FileResponse(cache_path, media_type="image/jpeg")


@router.get("", response_model=list[VideoOut])
async def list_videos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).order_by(Video.created_at.desc()).limit(50))
    return result.scalars().all()


@router.get("/{video_id}", response_model=VideoOut)
async def get_video(video_id: str, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    if video.status == "downloading" and video_id in _progress:
        video.progress = round(_progress[video_id], 1)
    return video


@router.delete("/{video_id}", status_code=204)
async def delete_video(video_id: str, db: AsyncSession = Depends(get_db)) -> None:
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    if video.path:
        Path(video.path).unlink(missing_ok=True)
    if video.thumbnail_path:
        Path(video.thumbnail_path).unlink(missing_ok=True)
    await db.delete(video)
    await db.commit()

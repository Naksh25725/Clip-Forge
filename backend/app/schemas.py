from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import get_settings


def to_media_url(stored: str | None) -> str:
    """Turn a stored filesystem path into a /media/... URL."""
    if not stored:
        return ""
    try:
        rel = Path(stored).resolve().relative_to(get_settings().data_dir.resolve())
        return "/media/" + rel.as_posix()
    except ValueError:
        return ""


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Source video ─────────────────────────────────────────────────────────
class VideoOut(ORMModel):
    id: str
    name: str
    source: str
    size_bytes: int
    duration: float
    width: int
    height: int
    fps: float
    codec: str
    thumbnail_path: str
    status: str
    progress: float
    error: str
    created_at: datetime

    @field_validator("thumbnail_path", mode="before")
    @classmethod
    def _thumb(cls, v: str) -> str:
        return to_media_url(v)


class LinkRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


# ── Splitting ────────────────────────────────────────────────────────────
class Overlay(BaseModel):
    """One burned-in text line. `y` runs 0 (top) to 1 (bottom); text may use
    {n} and {total} placeholders that expand per part."""

    text: str = Field("Part {n}", max_length=200)
    y: float = Field(0.85, ge=0.0, le=1.0)
    size: Literal["small", "medium", "large"] = "medium"


class SplitOptions(BaseModel):
    # "count"    = N equal parts across the whole video
    # "duration" = a new part every N seconds
    # "best"     = only the N most viral-worthy moments, with AI ratings
    mode: Literal["count", "duration", "best"] = "count"
    count: int = Field(4, ge=1, le=200)
    duration_seconds: int = Field(60, ge=3, le=7200)
    best_count: int = Field(5, ge=1, le=30)
    clip_length: int = Field(45, ge=5, le=600)

    # "source" keeps the original frame; "reel" makes a 9:16 vertical video.
    aspect: Literal["source", "reel"] = "source"
    # reel only: "crop" fills the screen; "fit" shows the whole frame on blur.
    reel_fill: Literal["crop", "fit"] = "crop"

    overlays: list[Overlay] = Field(default_factory=lambda: [Overlay()], max_length=6)

    quality: Literal["low", "medium", "high", "best"] = "high"
    resolution: Literal["source", "1080", "720", "480"] = "source"
    format: Literal["mp4", "mov", "webm"] = "mp4"

    ai_titles: bool = False
    # Burn spoken words onto each clip as plain subtitles (needs a transcript).
    subtitles: bool = False
    subtitle_y: float = Field(0.9, ge=0.2, le=0.98)
    # "auto" = Groq cloud when a key is set, otherwise local whisper.
    transcription: Literal["auto", "cloud", "local"] = "auto"

    output_mode: Literal["none", "local", "drive"] = "none"
    output_dir: str = ""
    drive_folder_id: str = "root"

    def resolve_overlays(self, index: int, total: int) -> list[dict]:
        resolved = []
        for overlay in self.overlays:
            text = (
                overlay.text.replace("{n}", str(index))
                .replace("{total}", str(total))
                .strip()
            )
            if text:
                resolved.append({"text": text, "y": overlay.y, "size": overlay.size})
        return resolved


class JobCreate(BaseModel):
    video_id: str
    options: SplitOptions = SplitOptions()


class PartOut(ORMModel):
    id: str
    job_id: str
    index: int
    label: str
    overlays: list
    title: str
    path: str
    thumbnail_path: str
    start_time: float
    end_time: float
    duration: float
    size_bytes: int
    status: str
    transcript: str
    subtitles: list
    viral_score: float
    viral_hook: float
    viral_reason: str
    viral_tier: str
    export_status: str
    export_target: str
    export_error: str
    created_at: datetime

    @field_validator("path", "thumbnail_path", mode="before")
    @classmethod
    def _media(cls, v: str) -> str:
        return to_media_url(v)


class JobOut(ORMModel):
    id: str
    video_id: str
    options: dict
    status: str
    progress: float
    message: str
    error: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobDetail(JobOut):
    video: VideoOut
    parts: list[PartOut] = []


class PartUpdate(BaseModel):
    """Changing `label` or `overlays` re-renders the part with new text."""

    label: str | None = Field(None, max_length=200)
    title: str | None = Field(None, max_length=200)
    overlays: list[Overlay] | None = Field(None, max_length=6)


class PreviewRequest(BaseModel):
    time: float = Field(1.0, ge=0.0)
    aspect: Literal["source", "reel"] = "source"
    reel_fill: Literal["crop", "fit"] = "crop"


class ExportRequest(BaseModel):
    part_ids: list[str] = []
    mode: Literal["local", "drive"] = "local"
    output_dir: str = ""
    drive_folder_id: str = "root"


# ── Settings ─────────────────────────────────────────────────────────────
class AppSettings(BaseModel):
    output_mode: Literal["none", "local", "drive"] = "local"
    output_dir: str = ""
    drive_folder_id: str = "root"
    label_template: str = "Part {n}"
    label_y: float = 0.85
    label_size: Literal["small", "medium", "large"] = "medium"
    aspect: Literal["source", "reel"] = "source"
    reel_fill: Literal["crop", "fit"] = "crop"
    subtitles: bool = False
    subtitle_y: float = 0.9
    transcription_mode: Literal["auto", "cloud", "local"] = "auto"
    quality: Literal["low", "medium", "high", "best"] = "high"
    resolution: Literal["source", "1080", "720", "480"] = "source"
    format: Literal["mp4", "mov", "webm"] = "mp4"


class AppSettingsUpdate(BaseModel):
    output_mode: str | None = None
    output_dir: str | None = None
    drive_folder_id: str | None = None
    label_template: str | None = None
    label_y: float | None = None
    label_size: str | None = None
    aspect: str | None = None
    reel_fill: str | None = None
    subtitles: bool | None = None
    subtitle_y: float | None = None
    transcription_mode: str | None = None
    quality: str | None = None
    resolution: str | None = None
    format: str | None = None


class FolderCheck(BaseModel):
    path: str


class FolderCheckResult(BaseModel):
    ok: bool
    resolved: str = ""
    message: str = ""


# ── Integrations ─────────────────────────────────────────────────────────
class DriveStatus(BaseModel):
    configured: bool
    connected: bool
    account_email: str = ""


class DriveFolder(BaseModel):
    id: str
    name: str


class CreateFolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent: str = "root"


class AiStatus(BaseModel):
    provider: str = "groq"
    has_key: bool
    model: str
    stt_model: str = ""
    ok: bool = False
    message: str = ""
    whisper_available: bool = False
    cloud_stt_available: bool = False

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Video(Base):
    """A source video — uploaded from disk or downloaded from a link."""

    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    name: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(16), default="upload")  # upload|link
    source_url: Mapped[str] = mapped_column(Text, default="")
    path: Mapped[str] = mapped_column(Text, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    fps: Mapped[float] = mapped_column(Float, default=0.0)
    codec: Mapped[str] = mapped_column(String(64), default="")
    thumbnail_path: Mapped[str] = mapped_column(Text, default="")
    # downloading | ready | error
    status: Mapped[str] = mapped_column(String(16), default="ready")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_now)

    jobs: Mapped[list["Job"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class Job(Base):
    """One split run over a video, producing N parts."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    # queued | running | done | error | cancelled
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_now)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    video: Mapped["Video"] = relationship(back_populates="jobs")
    parts: Mapped[list["Part"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Part(Base):
    """A rendered segment with its burned-in label."""

    __tablename__ = "parts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer, default=1)
    label: Mapped[str] = mapped_column(String(256), default="")  # first burned-in text
    # All burned-in texts: [{text, y (0..1), size}] — label mirrors overlays[0].
    overlays: Mapped[list] = mapped_column(JSON, default=list)
    title: Mapped[str] = mapped_column(String(256), default="")  # file / display name
    path: Mapped[str] = mapped_column(Text, default="")
    thumbnail_path: Mapped[str] = mapped_column(Text, default="")
    start_time: Mapped[float] = mapped_column(Float, default=0.0)
    end_time: Mapped[float] = mapped_column(Float, default=0.0)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # pending | rendering | ready | error
    status: Mapped[str] = mapped_column(String(16), default="pending")
    transcript: Mapped[str] = mapped_column(Text, default="")
    # Clip-relative timed subtitle events: [{start, end, text}].
    subtitles: Mapped[list] = mapped_column(JSON, default=list)
    # Populated in "best clips" mode.
    viral_score: Mapped[float] = mapped_column(Float, default=0.0)
    viral_hook: Mapped[float] = mapped_column(Float, default=0.0)
    viral_reason: Mapped[str] = mapped_column(Text, default="")
    viral_tier: Mapped[str] = mapped_column(
        String(16), default=""
    )  # ai|heuristic|signal
    # none | saving | saved | error
    export_status: Mapped[str] = mapped_column(String(16), default="none")
    export_target: Mapped[str] = mapped_column(Text, default="")
    export_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_now)

    job: Mapped["Job"] = relationship(back_populates="parts")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")

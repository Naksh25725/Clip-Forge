"""Async ffmpeg / ffprobe helpers, including burned-in part labels."""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings

logger = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    pass


async def _run(*cmd: str, timeout: float | None = None) -> tuple[bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise FFmpegError(f"Timed out: {' '.join(cmd[:4])}…")
    if proc.returncode != 0:
        raise FFmpegError(
            f"{cmd[0]} failed ({proc.returncode}): {stderr.decode(errors='replace')[-800:]}"
        )
    return stdout, stderr


@dataclass
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float
    codec: str
    size_bytes: int


async def probe(path: Path) -> VideoInfo:
    stdout, _ = await _run(
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
        timeout=120,
    )
    data = json.loads(stdout)
    fmt = data.get("format", {})
    stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"), {}
    )
    fps = 0.0
    try:
        num, den = str(stream.get("r_frame_rate", "0/1")).split("/")
        fps = round(float(num) / float(den), 2) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        pass
    return VideoInfo(
        duration=float(fmt.get("duration", 0.0) or 0.0),
        width=int(stream.get("width", 0) or 0),
        height=int(stream.get("height", 0) or 0),
        fps=fps,
        codec=str(stream.get("codec_name", "")),
        size_bytes=int(fmt.get("size", 0) or 0),
    )


# ── Label rendering ──────────────────────────────────────────────────────

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def resolve_font() -> str | None:
    configured = get_settings().font_file
    if configured and Path(configured).exists():
        return configured
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _escape_path(path: str) -> str:
    """Escape a filesystem path for use inside an ffmpeg filtergraph."""
    return path.replace("\\", "/").replace(":", r"\:")


def _escape_text(text: str) -> str:
    """Escape label text for drawtext (single quotes are swapped for a
    typographic apostrophe — they cannot be nested inside the quoted value)."""
    return (
        text.replace("\\", r"\\")
        .replace("'", "’")
        .replace(":", r"\:")
        .replace("%", r"\%")
    )


SIZE_FACTORS = {"small": 16.0, "medium": 11.0, "large": 8.0}

# Reel canvas per resolution setting (width, height) — always 9:16.
_REEL_DIMS = {
    "source": (1080, 1920),
    "1080": (1080, 1920),
    "720": (720, 1280),
    "480": (480, 852),
}


def build_drawtext(
    text: str,
    out_height: int,
    y: float = 0.85,
    size: str = "medium",
    color: str = "white",
    box: bool = True,
) -> str | None:
    """A drawtext filter: horizontally centered, `y` = 0 (top) .. 1 (bottom).

    y is a fraction of the *available* travel (h - text_h), which is exactly
    how the frontend preview positions its draggable text — the two agree.
    """
    font = resolve_font()
    if not font or not text.strip():
        if not font:
            logger.warning("No usable font found — skipping label burn-in")
        return None

    font_size = max(int(out_height / SIZE_FACTORS.get(size, 11.0)), 12)
    y = max(0.0, min(float(y), 1.0))
    parts = [
        f"fontfile='{_escape_path(font)}'",
        f"text='{_escape_text(text)}'",
        f"fontsize={font_size}",
        f"fontcolor={color}",
        "x=(w-text_w)/2",
        f"y=(h-text_h)*{y:.4f}",
        "shadowcolor=black@0.6",
        "shadowx=2",
        "shadowy=2",
    ]
    if box:
        parts += ["box=1", "boxcolor=black@0.45", f"boxborderw={max(font_size // 3, 8)}"]
    return "drawtext=" + ":".join(parts)


_QUALITY_CRF = {"low": 30, "medium": 26, "high": 21, "best": 18}


def output_height(source_height: int, resolution: str, aspect: str = "source") -> int:
    if aspect == "reel":
        return _REEL_DIMS.get(resolution, _REEL_DIMS["source"])[1]
    if resolution == "source" or not resolution:
        return source_height or 1080
    try:
        return int(resolution)
    except ValueError:
        return source_height or 1080


def output_dimensions(
    source_height: int, resolution: str, aspect: str, source_width: int
) -> tuple[int, int]:
    """Final (width, height) of the rendered frame — needed to size subtitles."""
    if aspect == "reel":
        return _REEL_DIMS.get(resolution, _REEL_DIMS["source"])
    h = output_height(source_height, resolution, aspect)
    src_w = source_width or 1920
    src_h = source_height or 1080
    w = round(src_w * (h / src_h) / 2) * 2  # keep width even for yuv420p
    return w, h


def _geometry(aspect: str, reel_fill: str, resolution: str) -> tuple[list[str], str]:
    """(simple -vf chain, filter_complex) — exactly one of the two is used.

    aspect "reel" turns any input into a 9:16 canvas:
      reel_fill "crop" — scale up and center-crop, filling the screen
      reel_fill "fit"  — whole video centered over a blurred, filled copy
    """
    if aspect != "reel":
        if resolution != "source":
            return [f"scale=-2:{int(resolution)}"], ""
        return [], ""

    width, height = _REEL_DIMS.get(resolution, _REEL_DIMS["source"])
    if reel_fill == "fit":
        complex_graph = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=20:2,eq=brightness=-0.08[bgb];"
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease:"
            f"force_divisible_by=2[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2"
        )
        return [], complex_graph
    return [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
    ], ""


def _escape_subtitle_path(path: str) -> str:
    """Escape an .ass path for the `subtitles` filter.

    On Windows the drive-letter colon and backslashes are the usual failure —
    forward slashes and an escaped colon are what libass accepts inside a
    filtergraph value.
    """
    return path.replace("\\", "/").replace(":", r"\:")


def _subtitles_filter(subtitle_path: Path) -> str:
    return f"subtitles='{_escape_subtitle_path(str(subtitle_path))}'"


def _overlay_filters(overlays: list[dict], out_height: int) -> list[str]:
    filters: list[str] = []
    for overlay in overlays or []:
        drawtext = build_drawtext(
            str(overlay.get("text", "")),
            out_height,
            y=float(overlay.get("y", 0.85)),
            size=str(overlay.get("size", "medium")),
        )
        if drawtext:
            filters.append(drawtext)
    return filters


async def render_part(
    src: Path,
    dst: Path,
    start: float,
    end: float,
    overlays: list[dict] | None = None,
    subtitle_path: Path | None = None,
    aspect: str = "source",
    reel_fill: str = "crop",
    source_height: int = 1080,
    quality: str = "high",
    resolution: str = "source",
    fmt: str = "mp4",
) -> None:
    """Cut [start, end] out of `src`, apply the reel transform and burn text.

    Filter order matters: geometry first, then subtitles (so they sit on the
    final canvas), then the draggable overlays on top.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    crf = _QUALITY_CRF.get(quality, 21)

    out_h = output_height(source_height, resolution, aspect)
    vf_chain, complex_graph = _geometry(aspect, reel_fill, resolution)
    sub_filters = [_subtitles_filter(subtitle_path)] if subtitle_path else []
    text_filters = _overlay_filters(overlays or [], out_h)

    args: list[str] = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(src),
    ]
    if complex_graph:
        tail = sub_filters + text_filters
        graph = complex_graph + ("," + ",".join(tail) if tail else "")
        args += ["-filter_complex", f"{graph}[vout]", "-map", "[vout]", "-map", "0:a?"]
    else:
        filters = vf_chain + sub_filters + text_filters
        if filters:
            args += ["-vf", ",".join(filters)]

    if fmt == "webm":
        args += ["-c:v", "libvpx-vp9", "-crf", str(crf), "-b:v", "0", "-c:a", "libopus"]
    else:
        args += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
        ]
    args.append(str(dst))
    await _run(*args, timeout=7200)


async def preview_frame(
    src: Path,
    at: float,
    aspect: str = "source",
    reel_fill: str = "crop",
    dst: Path | None = None,
) -> bytes:
    """One JPEG frame with the same geometry the final render will use.

    Text is *not* burned in here — the frontend draws draggable overlays on
    top of this image so positioning feels instant.
    """
    import tempfile

    vf_chain, complex_graph = _geometry(aspect, reel_fill, "720")
    args: list[str] = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{max(at, 0):.3f}", "-i", str(src), "-frames:v", "1", "-q:v", "4",
    ]
    if complex_graph:
        args += ["-filter_complex", f"{complex_graph}[vout]", "-map", "[vout]"]
    elif vf_chain:
        args += ["-vf", ",".join(vf_chain)]
    else:
        args += ["-vf", "scale=-2:720"]

    if dst is not None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        args.append(str(dst))
        await _run(*args, timeout=120)
        return dst.read_bytes()

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "preview.jpg"
        args.append(str(out))
        await _run(*args, timeout=120)
        return out.read_bytes()


async def make_thumbnail(src: Path, dst: Path, at: float = 1.0, height: int = 400) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    await _run(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{max(at, 0):.3f}", "-i", str(src),
        "-frames:v", "1", "-vf", f"scale=-2:{height}", "-q:v", "3", str(dst),
        timeout=180,
    )


async def extract_audio_wav(src: Path, dst: Path) -> None:
    """16 kHz mono WAV — what faster-whisper ingests fastest."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    await _run(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(dst),
        timeout=3600,
    )


async def scene_change_times(src: Path, threshold: float = 0.35) -> list[float]:
    """Timestamps of visual cuts, in a single downscaled decode pass."""
    _, stderr = await _run(
        "ffmpeg", "-hide_banner", "-i", str(src), "-an",
        # Scaling down first makes the scene filter dramatically cheaper.
        "-vf", f"scale=-2:180,select='gt(scene,{threshold})',showinfo",
        "-f", "null", os.devnull,
        timeout=3600,
    )
    return [
        float(m.group(1))
        for m in re.finditer(rb"pts_time:([\d.]+)", stderr)
    ]


def rms_by_window(wav_path: Path, windows: list[tuple[float, float]]) -> list[float]:
    """Average loudness per window, read straight from the 16 kHz mono WAV.

    Sampling every ~16th frame keeps this fast on long videos while staying
    accurate enough to rank one window against another.
    """
    import array
    import math
    import wave

    try:
        with wave.open(str(wav_path), "rb") as handle:
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, OSError):
        return [0.0] * len(windows)

    samples = array.array("h")
    try:
        samples.frombytes(frames)
    except ValueError:
        return [0.0] * len(windows)

    step = max(rate // 1000, 1)
    results: list[float] = []
    for start, end in windows:
        lo = max(int(start * rate), 0)
        hi = min(int(end * rate), len(samples))
        if hi <= lo:
            results.append(0.0)
            continue
        total = 0
        count = 0
        for i in range(lo, hi, step):
            value = samples[i]
            total += value * value
            count += 1
        results.append(math.sqrt(total / count) if count else 0.0)
    return results

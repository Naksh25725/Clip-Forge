"""Cloud transcription via Groq's hosted Whisper (free tier).

Same output shape as the local path: timestamped Segment objects. The audio is
compressed to a small mono MP3 first (an hour ≈ 14 MB) and split into chunks
under Groq's per-upload cap, with each chunk's timestamps shifted back into
video time.
"""

import logging
from collections.abc import Callable
from pathlib import Path

import httpx

from ..config import get_secrets, get_settings
from .transcription import Segment

logger = logging.getLogger(__name__)

TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
CHUNK_SECONDS = 3000  # 50 min of 32 kbps mono ≈ 12 MB — safely under the cap


class CloudSTTError(RuntimeError):
    pass


def available() -> bool:
    return bool(get_secrets().groq_api_key)


async def _compress_chunk(src: Path, dst: Path, start: float, duration: float) -> None:
    from . import ffmpeg

    await ffmpeg._run(  # noqa: SLF001 — same package, deliberate reuse
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "32k",
        str(dst),
        timeout=1800,
    )


async def _transcribe_chunk(
    client: httpx.AsyncClient, path: Path, offset: float
) -> list[Segment]:
    settings = get_settings()
    response = await client.post(
        TRANSCRIBE_URL,
        headers={"Authorization": f"Bearer {get_secrets().groq_api_key}"},
        files={"file": (path.name, path.read_bytes(), "audio/mpeg")},
        data={
            "model": settings.groq_stt_model,
            "response_format": "verbose_json",
            "temperature": "0",
        },
    )
    if response.status_code != 200:
        raise CloudSTTError(
            f"Groq transcription returned {response.status_code}: {response.text[:300]}"
        )
    payload = response.json()
    segments = []
    for seg in payload.get("segments") or []:
        text = str(seg.get("text", "")).strip()
        if text:
            segments.append(
                Segment(
                    start=float(seg.get("start", 0.0)) + offset,
                    end=float(seg.get("end", 0.0)) + offset,
                    text=text,
                )
            )
    # A response with plain text but no segments is still usable as one block.
    if not segments and (payload.get("text") or "").strip():
        segments.append(Segment(start=offset, end=offset, text=payload["text"].strip()))
    return segments


async def transcribe(
    wav_path: Path,
    duration: float,
    workdir: Path,
    on_progress: Callable[[float, str], None] | None = None,
) -> list[Segment]:
    """Transcribe `wav_path` in Groq's cloud. Raises CloudSTTError on failure."""
    if not available():
        raise CloudSTTError("No GROQ_API_KEY configured")

    duration = max(duration, 0.5)
    chunk_count = max(int(duration // CHUNK_SECONDS) + 1, 1)
    chunk_length = duration / chunk_count

    all_segments: list[Segment] = []
    async with httpx.AsyncClient(timeout=300) as client:
        for i in range(chunk_count):
            start = i * chunk_length
            if on_progress:
                on_progress(
                    i / chunk_count,
                    f"Uploading audio to Groq ({i + 1}/{chunk_count})"
                    if chunk_count > 1
                    else "Transcribing in the cloud (Groq)",
                )
            chunk_path = workdir / f"stt_chunk_{i}.mp3"
            await _compress_chunk(wav_path, chunk_path, start, chunk_length + 1.0)
            try:
                all_segments.extend(await _transcribe_chunk(client, chunk_path, start))
            except httpx.HTTPError as exc:
                raise CloudSTTError(f"Could not reach Groq: {exc}") from exc
            finally:
                chunk_path.unlink(missing_ok=True)

    if on_progress:
        on_progress(1.0, "Cloud transcription finished")
    all_segments.sort(key=lambda s: s.start)
    logger.info(
        "Cloud transcription: %d segments from %d chunk(s)",
        len(all_segments),
        chunk_count,
    )
    return all_segments

"""Speech-to-text via faster-whisper. Model is loaded lazily and cached."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings

logger = logging.getLogger(__name__)

_model = None
_model_lock = asyncio.Lock()


@dataclass
class Segment:
    start: float
    end: float
    text: str


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


async def _get_model():
    global _model
    async with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel

            settings = get_settings()
            compute = "int8" if settings.whisper_device == "cpu" else "float16"
            logger.info(
                "Loading whisper model %s (%s)", settings.whisper_model, compute
            )
            _model = await asyncio.to_thread(
                WhisperModel,
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=compute,
            )
    return _model


def _transcribe_sync(
    model,
    path: str,
    language: str | None,
    on_progress: Callable[[float], None] | None = None,
) -> list[Segment]:
    segments, info = model.transcribe(
        path,
        language=language,
        vad_filter=True,
        beam_size=5,
    )
    total = max(float(getattr(info, "duration", 0.0) or 0.0), 0.1)
    result: list[Segment] = []
    reported = 0.0
    # `segments` is a generator — consuming it performs the transcription, so
    # each iteration is a natural progress tick.
    for s in segments:
        result.append(Segment(start=s.start, end=s.end, text=s.text.strip()))
        if on_progress:
            fraction = min(s.end / total, 1.0)
            if fraction - reported >= 0.02:  # throttle to ~50 updates max
                reported = fraction
                try:
                    on_progress(fraction)
                except Exception:  # noqa: BLE001 — progress must never kill the run
                    logger.exception("Transcription progress callback failed")
    if on_progress and reported < 1.0:
        try:
            on_progress(1.0)
        except Exception:  # noqa: BLE001
            pass
    return result


async def transcribe(
    path: Path,
    language: str | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> list[Segment]:
    """Transcribe a file into timestamped segments.

    `on_progress` receives a 0..1 fraction and is called from a worker
    thread — pass something thread-safe.
    """
    settings = get_settings()
    if not settings.whisper_enabled or not whisper_available():
        logger.info("Transcription skipped (disabled or faster-whisper not installed)")
        return []
    model = await _get_model()
    lang = None if language in (None, "", "auto") else language
    return await asyncio.to_thread(
        _transcribe_sync, model, str(path), lang, on_progress
    )

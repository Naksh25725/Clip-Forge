"""Find the moments in a video most likely to work as short-form clips.

Three tiers, picked automatically by what's available:

  1. Groq key + transcript → the LLM rates each candidate (best quality)
  2. transcript only       → text heuristics (hooks, emotion, pace) + signals
  3. neither               → audio loudness + visual cut density only

Every tier produces a 0-100 score and a sentence explaining it, so the UI can
always show the user why a clip was picked.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import ai, ffmpeg

logger = logging.getLogger(__name__)

HOOK_PATTERNS = [
    r"\bwhat if\b", r"\bimagine\b", r"\bhere'?s (?:why|how|the)\b", r"\bsecret\b",
    r"\bnobody\b", r"\byou won'?t believe\b", r"\bthe (?:biggest|best|worst)\b",
    r"\bmistake\b", r"\bnever\b", r"\balways\b", r"\bwhy\b", r"\bhow to\b",
    r"\btop \d+\b", r"\bthe truth\b", r"\bactually\b", r"\bturns out\b", r"\?",
]
EMOTION_WORDS = {
    "amazing", "incredible", "insane", "crazy", "love", "hate", "wow", "shocking",
    "unbelievable", "terrifying", "hilarious", "beautiful", "awesome", "horrible",
    "excited", "afraid", "angry", "happy", "sad", "huge", "massive", "wild",
    "perfect", "worst", "best", "epic", "brutal", "stunning", "obsessed",
}

# Longest transcript we hand to the LLM in one request.
MAX_AI_CANDIDATES = 24


@dataclass
class Candidate:
    start: float
    end: float
    text: str = ""
    score: float = 0.0
    hook: float = 0.0
    reason: str = ""
    title: str = ""
    tier: str = "signal"  # signal | heuristic | ai
    parts: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end - self.start


def _normalize(values: list[float]) -> list[float]:
    """Map raw measurements onto 0-100 relative to each other."""
    if not values:
        return []
    low, high = min(values), max(values)
    if high - low < 1e-9:
        return [50.0] * len(values)
    return [(v - low) / (high - low) * 100 for v in values]


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class _Unit:
    start: float
    end: float
    text: str


def sentence_units(segments: list) -> list[_Unit]:
    """Split transcript segments into individual sentences.

    Whisper often merges several sentences into one segment. Since a clip can
    only begin where a unit begins, that would force a clip to open on the
    filler sentence sitting in front of the hook. Timing inside a segment is
    apportioned by character count, which tracks speech rate closely enough.
    """
    units: list[_Unit] = []
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        sentences = [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]
        span = max(seg.end - seg.start, 0.0)
        if len(sentences) <= 1 or span <= 0:
            units.append(_Unit(seg.start, seg.end, text))
            continue
        total_chars = sum(len(s) for s in sentences)
        cursor = seg.start
        for sentence in sentences:
            share = span * (len(sentence) / total_chars) if total_chars else span / len(sentences)
            end = min(cursor + share, seg.end)
            units.append(_Unit(cursor, end, sentence))
            cursor = end
    return units


def build_candidates(
    duration: float,
    target_length: float,
    segments: list,
) -> list[Candidate]:
    """Overlapping windows of roughly `target_length`, snapped to speech when
    a transcript is available so clips don't start mid-sentence."""
    target_length = max(min(target_length, duration), 5.0)
    # A fine stride matters: it's what lets a clip start exactly on the hook
    # line instead of a few sentences before it.
    stride = max(target_length / 4, 2.0)
    segments = sentence_units(segments)

    if not segments:
        windows: list[Candidate] = []
        start = 0.0
        while start < duration - 2.0:
            windows.append(Candidate(start=start, end=min(start + target_length, duration)))
            start += stride
        return windows or [Candidate(start=0.0, end=duration)]

    candidates: list[Candidate] = []
    last_start = -stride
    for i, seg in enumerate(segments):
        if seg.start - last_start < stride:
            continue
        last_start = seg.start
        end = min(seg.start + target_length, duration)
        # Extend to the end of the sentence we'd otherwise cut off.
        chunk: list[str] = []
        actual_end = end
        for later in segments[i:]:
            if later.start >= end:
                break
            chunk.append(later.text)
            actual_end = min(later.end, duration)
        if actual_end - seg.start < 3.0:
            continue
        candidates.append(
            Candidate(start=seg.start, end=actual_end, text=" ".join(chunk).strip())
        )
    return candidates or [Candidate(start=0.0, end=duration)]


def _text_scores(text: str, duration: float) -> tuple[float, float, str]:
    """(engagement, hook, explanation) from the transcript alone."""
    words = re.findall(r"[\w']+", text.lower())
    if not words:
        return 0.0, 0.0, "No speech in this stretch."

    # A hook only works if it lands in the first breath. Phrases further in
    # still count, but at half credit — that's what makes a window starting
    # *on* the hook outrank one that wanders into it a sentence later.
    opening = " ".join(words[:8])
    followup = " ".join(words[8:20])
    early_hits = sum(1 for p in HOOK_PATTERNS if re.search(p, opening))
    late_hits = sum(1 for p in HOOK_PATTERNS if re.search(p, followup))
    hook_hits = early_hits + late_hits
    hook = min(20 + early_hits * 24 + late_hits * 12, 100)

    emotion_hits = sum(1 for w in words if w in EMOTION_WORDS)
    emotion = min((emotion_hits / len(words)) * 900 + text.count("!") * 8, 100)

    pace = len(words) / max(duration, 1) * 60
    pace_score = max(0.0, min((pace - 60) / 120 * 100, 100))

    # Short-form lives or dies on the first seconds, so the hook dominates.
    # Weighted any flatter and a clip that merely *contains* a great line beats
    # the one that opens with it.
    engagement = hook * 0.55 + emotion * 0.25 + pace_score * 0.20
    where = "right at the start" if early_hits else "shortly in" if late_hits else ""
    reason = (
        f"{hook_hits} hook phrase{'s' if hook_hits != 1 else ''}"
        + (f" {where}" if where else "")
        + f", {emotion_hits} emotive word{'s' if emotion_hits != 1 else ''}, "
        f"{pace:.0f} words/min."
    )
    return engagement, hook, reason


async def _apply_ai_scores(
    candidates: list[Candidate],
    energy: list[float],
    motion: list[float],
) -> None:
    """Pre-rank with heuristics so the LLM only sees the strongest candidates, then assign AI scores."""
    shortlist = sorted(
        range(len(candidates)),
        key=lambda i: _text_scores(candidates[i].text, candidates[i].duration)[0]
        + energy[i] * 0.3,
        reverse=True,
    )[:MAX_AI_CANDIDATES]
    shortlist.sort()

    ai_results = await ai.rate_clips([candidates[i].text for i in shortlist])
    if not ai_results:
        return

    for slot, idx in enumerate(shortlist):
        if slot >= len(ai_results):
            break
        result = ai_results[slot]
        candidate = candidates[idx]
        signal = energy[idx] * 0.6 + motion[idx] * 0.4
        candidate.score = result["score"] * 0.75 + signal * 0.25
        candidate.hook = result["hook"]
        candidate.reason = result["reason"] or "Rated by AI."
        candidate.title = result["title"]
        candidate.tier = "ai"
        candidate.parts = {
            "ai_score": round(result["score"], 1),
            "energy": round(energy[idx], 1),
            "motion": round(motion[idx], 1),
        }


def _apply_heuristic_scores(
    candidates: list[Candidate],
    energy: list[float],
    motion: list[float],
) -> None:
    """Fallback to heuristic scoring for candidates not rated by AI."""
    for i, candidate in enumerate(candidates):
        if candidate.tier == "ai":
            continue
        if candidate.text.strip():
            engagement, hook, why = _text_scores(candidate.text, candidate.duration)
            candidate.score = engagement * 0.70 + energy[i] * 0.20 + motion[i] * 0.10
            candidate.hook = hook
            candidate.tier = "heuristic"
            candidate.reason = f"{why} Energy {energy[i]:.0f}/100."
        else:
            candidate.score = energy[i] * 0.65 + motion[i] * 0.35
            candidate.hook = energy[i]
            candidate.tier = "signal"
            candidate.reason = (
                f"Scored on audio energy ({energy[i]:.0f}/100) and visual activity "
                f"({motion[i]:.0f}/100) — no transcript available."
            )
        candidate.parts = {"energy": round(energy[i], 1), "motion": round(motion[i], 1)}


async def score_candidates(
    candidates: list[Candidate],
    wav_path: Path | None,
    scene_times: list[float],
    use_ai: bool,
) -> list[Candidate]:
    """Attach a 0-100 viral score and an explanation to every candidate."""
    if not candidates:
        return []

    windows = [(c.start, c.end) for c in candidates]

    # Audio energy — a proxy for delivery intensity.
    energy = [0.0] * len(candidates)
    if wav_path and wav_path.exists():
        try:
            energy = _normalize(ffmpeg.rms_by_window(wav_path, windows))
        except Exception:  # noqa: BLE001
            logger.warning("Loudness analysis failed", exc_info=True)

    # Visual cut density — a proxy for how much is happening on screen.
    motion_raw = [
        sum(1 for t in scene_times if c.start <= t < c.end) / max(c.duration / 60, 0.1)
        for c in candidates
    ]
    motion = _normalize(motion_raw) if scene_times else [0.0] * len(candidates)

    has_text = any(c.text.strip() for c in candidates)

    if use_ai and has_text:
        await _apply_ai_scores(candidates, energy, motion)

    _apply_heuristic_scores(candidates, energy, motion)

    return candidates


def pick_best(candidates: list[Candidate], count: int, min_gap: float = 1.0) -> list[Candidate]:
    """Highest-scoring candidates that don't overlap each other."""
    chosen: list[Candidate] = []
    for candidate in sorted(candidates, key=lambda c: c.score, reverse=True):
        if len(chosen) >= count:
            break
        if any(
            candidate.start < picked.end + min_gap and picked.start < candidate.end + min_gap
            for picked in chosen
        ):
            continue
        chosen.append(candidate)
    chosen.sort(key=lambda c: c.start)
    return chosen

"""AI part naming via Groq's free tier (OpenAI-compatible chat completions).

Get a key at https://console.groq.com/keys and set GROQ_API_KEY.
Without a key this module is a no-op and parts keep their numbered labels.
"""

import json
import logging

import httpx

from ..config import get_secrets, get_settings

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODELS_URL = "https://api.groq.com/openai/v1/models"

SYSTEM_PROMPT = (
    "You name short video clips cut from a longer video. For each numbered part "
    "you get its transcript. Reply with a punchy title of at most 6 words that "
    "says what actually happens in that part. No quotes, no emoji, no numbering."
)


def has_key() -> bool:
    return bool(get_secrets().groq_api_key)


async def check_key() -> tuple[bool, str]:
    """Validate the configured key against Groq. Returns (ok, message)."""
    key = get_secrets().groq_api_key
    if not key:
        return False, "No GROQ_API_KEY set"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                MODELS_URL, headers={"Authorization": f"Bearer {key}"}
            )
        if response.status_code == 200:
            return True, "Connected"
        if response.status_code == 401:
            return False, "Invalid API key"
        return False, f"Groq returned {response.status_code}"
    except httpx.HTTPError as exc:
        return False, f"Could not reach Groq: {exc}"


RATING_PROMPT = (
    "You rate moments cut from a longer video for short-form viral potential "
    "on TikTok, Reels and YouTube Shorts. Judge each candidate on: how hard the "
    "opening line hooks a scrolling viewer, whether it delivers a complete "
    "payoff on its own, emotional charge, and how quotable it is. Be honest — "
    "most moments are mediocre, so use the full 0-100 range and reserve scores "
    "above 80 for genuinely standout clips."
)


async def rate_clips(candidates: list[str]) -> list[dict]:
    """Score candidate moments for viral potential.

    Each result: {score, hook, reason, title}. Returns [] when Groq is
    unavailable so the caller can fall back to signal-only scoring.
    """
    key = get_secrets().groq_api_key
    if not key or not candidates:
        return []

    numbered = "\n\n".join(
        f"Candidate {i + 1}: {(text.strip() or '(no speech)')[:1200]}"
        for i, text in enumerate(candidates)
    )
    payload = {
        "model": get_settings().groq_model,
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": RATING_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{numbered}\n\nReturn JSON shaped exactly like "
                    '{"clips": [{"score": 0-100, "hook": 0-100, '
                    '"reason": "one concrete sentence", "title": "max 6 words"}]} '
                    f"with exactly {len(candidates)} entries, in the same order."
                ),
            },
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                GROQ_URL, headers={"Authorization": f"Bearer {key}"}, json=payload
            )
        if response.status_code != 200:
            logger.warning("Groq rating error %s: %s", response.status_code, response.text[:300])
            return []
        content = response.json()["choices"][0]["message"]["content"]
        clips = json.loads(content).get("clips", [])
        results: list[dict] = []
        for entry in clips[: len(candidates)]:
            if not isinstance(entry, dict):
                entry = {}
            results.append(
                {
                    "score": max(0.0, min(float(entry.get("score", 0) or 0), 100.0)),
                    "hook": max(0.0, min(float(entry.get("hook", 0) or 0), 100.0)),
                    "reason": str(entry.get("reason", "")).strip()[:400],
                    "title": str(entry.get("title", "")).strip().strip('"')[:80],
                }
            )
        return results
    except Exception:  # noqa: BLE001 — rating is best-effort
        logger.exception("Groq clip rating failed")
        return []


async def generate_titles(transcripts: list[str]) -> list[str]:
    """Return one title per transcript. Empty strings where unavailable."""
    key = get_secrets().groq_api_key
    blanks = [""] * len(transcripts)
    if not key or not any(t.strip() for t in transcripts):
        return blanks

    numbered = "\n\n".join(
        f"Part {i + 1}: {(text.strip() or '(no speech)')[:1500]}"
        for i, text in enumerate(transcripts)
    )
    payload = {
        "model": get_settings().groq_model,
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{numbered}\n\nReturn JSON shaped exactly like "
                    '{"titles": ["title for part 1", "title for part 2", ...]} '
                    f"with exactly {len(transcripts)} titles, in order."
                ),
            },
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
            )
        if response.status_code != 200:
            logger.warning("Groq error %s: %s", response.status_code, response.text[:300])
            return blanks
        content = response.json()["choices"][0]["message"]["content"]
        titles = json.loads(content).get("titles", [])
        cleaned = [str(t).strip().strip('"')[:80] for t in titles]
        cleaned += [""] * (len(transcripts) - len(cleaned))
        return cleaned[: len(transcripts)]
    except Exception:  # noqa: BLE001 — naming is best-effort
        logger.exception("Groq title generation failed")
        return blanks

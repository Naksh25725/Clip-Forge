"""Generate ASS subtitle files from timed transcript segments.

Plain subtitles: a line or two near the bottom that change as the speaker
talks. Timings come straight from Whisper, shifted so each clip starts at 0.
"""

import textwrap
from pathlib import Path

# ASS colours are &HAABBGGRR (alpha, blue, green, red).
_WHITE = "&H00FFFFFF"
_BLACK = "&H00000000"
_SHADOW = "&H80000000"

# Subtitle text is smaller than the big part label.
_FONT_DIVISOR = 20
_MAX_CHARS_PER_LINE = 38


def _ass_time(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _wrap(text: str) -> str:
    lines = textwrap.wrap(text.strip(), width=_MAX_CHARS_PER_LINE, max_lines=2, placeholder="…")
    return "\\N".join(lines)  # \N is a hard line break in ASS


def _sanitize(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def has_subtitle_lines(segments: list[dict]) -> bool:
    return any(str(s.get("text", "")).strip() for s in segments)


def build_ass(
    segments: list[dict],
    width: int,
    height: int,
    dst: Path,
    y: float = 0.9,
    font: str = "Arial",
) -> Path | None:
    """Write an ASS file for clip-relative `segments` ([{start, end, text}]).

    `y` is where the caption sits, 0 (top) to 1 (bottom) — the same fraction the
    preview uses, so the burn matches what the user dragged. Returns the path,
    or None when there's nothing to show.
    """
    events = [s for s in segments if str(s.get("text", "")).strip()]
    if not events:
        return None

    font_size = max(int(height / _FONT_DIVISOR), 14)
    outline = max(round(height / 400), 2)
    # Alignment 2 (bottom-centre): MarginV is the gap from the bottom edge, so
    # the caption's bottom lands at y·height from the top.
    y = min(max(y, 0.2), 0.98)
    margin_v = max(int((1.0 - y) * height), 12)

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{font_size},{_WHITE},{_WHITE},{_BLACK},{_SHADOW},"
        f"-1,0,0,0,100,100,0,0,1,{outline},1,2,40,40,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )

    lines = [header]
    for seg in events:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        if end <= start:
            end = start + 1.2  # a lone word still needs a readable dwell
        text = _wrap(_sanitize(str(seg["text"])))
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}\n"
        )

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("".join(lines), encoding="utf-8")
    return dst


def slice_segments(segments, start: float, end: float) -> list[dict]:
    """Return video-time Segments overlapping [start, end] as clip-relative dicts."""
    clip_length = end - start
    out: list[dict] = []
    for seg in segments:
        if seg.end <= start or seg.start >= end:
            continue
        rel_start = max(seg.start - start, 0.0)
        rel_end = min(seg.end - start, clip_length)
        if rel_end - rel_start < 0.05:
            continue
        out.append({"start": round(rel_start, 3), "end": round(rel_end, 3), "text": seg.text})
    return out

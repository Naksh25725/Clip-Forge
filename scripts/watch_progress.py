"""ClipForge live progress console.

Run `watch.bat` (or `python scripts/watch_progress.py`) in its own window and
leave it open — it shows a live progress bar, elapsed time and a time-left
estimate for whatever job is running. Uses only the Python standard library.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone

API = os.environ.get("CLIPFORGE_API", "http://127.0.0.1:8000")
BAR_WIDTH = 34
POLL_SECONDS = 2.0

os.system("")  # enables ANSI escape codes in the Windows console


def fetch_jobs():
    with urllib.request.urlopen(f"{API}/api/jobs?limit=5", timeout=5) as response:
        return json.loads(response.read())


def parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def fmt_span(seconds):
    seconds = max(int(seconds), 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def bar(progress):
    filled = int(BAR_WIDTH * min(max(progress, 0), 100) / 100)
    return "█" * filled + "░" * (BAR_WIDTH - filled)


def write_line(text):
    width = max(os.get_terminal_size().columns - 1, 40) if sys.stdout.isatty() else 120
    sys.stdout.write("\r" + text[:width].ljust(width))
    sys.stdout.flush()


def main():
    print("╔══════════════════════════════════════════════╗")
    print("║        ClipForge — live progress             ║")
    print("║   leave this window open; Ctrl+C to close    ║")
    print("╚══════════════════════════════════════════════╝")

    current_id = None
    samples = deque()  # (monotonic_time, progress) for the ETA rate
    announced_done = set()

    while True:
        try:
            jobs = fetch_jobs()
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            write_line("⚠  Backend not reachable — start ClipForge with start.bat …")
            time.sleep(3)
            continue

        active = next((j for j in jobs if j["status"] in ("running", "queued")), None)

        if active is None:
            # Announce the most recent finished job exactly once.
            latest = jobs[0] if jobs else None
            if latest and latest["id"] not in announced_done and latest["status"] in (
                "done", "error", "cancelled"
            ):
                announced_done.add(latest["id"])
                started = parse_time(latest.get("started_at"))
                finished = parse_time(latest.get("finished_at"))
                took = (
                    f" in {fmt_span((finished - started).total_seconds())}"
                    if started and finished
                    else ""
                )
                icon = {"done": "✔", "error": "✘", "cancelled": "⊘"}[latest["status"]]
                write_line("")
                detail = latest.get("error") or latest.get("message") or ""
                print(f"\r{icon} Job {latest['id'][:8]} {latest['status']}{took}  {detail[:60]}")
            write_line("…  idle — waiting for the next job")
            current_id = None
            samples.clear()
            time.sleep(POLL_SECONDS)
            continue

        if active["id"] != current_id:
            current_id = active["id"]
            samples.clear()
            write_line("")
            print(f"\r▶ Job {active['id'][:8]} started at {datetime.now():%H:%M:%S}")

        progress = float(active.get("progress", 0.0))
        now = time.monotonic()
        samples.append((now, progress))
        while samples and now - samples[0][0] > 90:  # sliding 90s rate window
            samples.popleft()

        eta_text = "estimating…"
        if len(samples) >= 2:
            dt = samples[-1][0] - samples[0][0]
            dp = samples[-1][1] - samples[0][1]
            if dt > 8 and dp > 0.3:
                rate = dp / dt  # percent per second
                eta_text = f"~{fmt_span((100 - progress) / rate)} left"
            elif dt > 30 and dp <= 0.3:
                eta_text = "working…"  # long silent stage (e.g. one huge render)

        started = parse_time(active.get("started_at"))
        elapsed = (
            fmt_span((datetime.now(timezone.utc) - started).total_seconds())
            if started
            else "0:00"
        )
        message = active.get("message") or ("waiting in queue" if active["status"] == "queued" else "starting")

        write_line(
            f"{bar(progress)} {progress:5.1f}%  {elapsed} elapsed · {eta_text}  │ {message}"
        )
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nbye 👋")

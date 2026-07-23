"""ClipForge launcher — one window that runs everything.

Starts the backend engine and the web app as child processes, opens the
browser, and shows live progress. Everything is placed inside a Windows job
object with KILL_ON_JOB_CLOSE, so when this window closes (the X button, Ctrl+C,
or a crash) the OS tears down the engine and web app too. Nothing is left
running in the background.

Standard library only.
"""

import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
LOG_DIR = ROOT / "backend" / "data" / "logs"
API = "http://127.0.0.1:8000"
WEB = "http://localhost:3000"
BAR = 32

os.system("")  # enable ANSI colours in the console


# ── Windows job object: children die when this process dies ───────────────
def _bind_children_to_this_process() -> object | None:
    if os.name != "nt":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class BASIC(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class EXTENDED(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC),
                ("IoInfo", IO),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        JobObjectExtendedLimitInformation = 9

        # Set signatures — without these, ctypes truncates the 64-bit HANDLE to
        # a 32-bit int and every job call silently fails.
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
        ):
            return None
        if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
            return None
        return job  # keep a reference alive; closing it triggers the kill
    except Exception:  # noqa: BLE001 — if this fails we still run, just less tidy
        return None


# ── small helpers ─────────────────────────────────────────────────────────
def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def api_ok() -> bool:
    try:
        with urllib.request.urlopen(f"{API}/api/health", timeout=2) as r:
            return json.loads(r.read()).get("status") == "ok"
    except Exception:  # noqa: BLE001
        return False


def fmt_span(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_time(value):
    if not value:
        return None
    try:
        t = datetime.fromisoformat(value)
        return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
    except ValueError:
        return None


def write_line(text: str) -> None:
    width = 118
    try:
        width = max(os.get_terminal_size().columns - 1, 40)
    except OSError:
        pass
    sys.stdout.write("\r" + text[:width].ljust(width))
    sys.stdout.flush()


def tail(path: Path, lines: int = 12) -> str:
    try:
        return "".join(path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)[-lines:])
    except OSError:
        return "(no log)"


# ── main ──────────────────────────────────────────────────────────────────
def main() -> int:
    job = _bind_children_to_this_process()  # noqa: F841 — must stay referenced
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    backend_log = LOG_DIR / "engine.log"
    frontend_log = LOG_DIR / "webapp.log"

    print(c("╔══════════════════════════════════════════════╗", "38;5;99"))
    print(c("║", "38;5;99") + "                 ClipForge                    " + c("║", "38;5;99"))
    print(c("║", "38;5;99") + c("   This window runs everything.               ", "37") + c("║", "38;5;99"))
    print(c("║", "38;5;99") + c("   Close it (or press Ctrl+C) to stop.        ", "90") + c("║", "38;5;99"))
    print(c("╚══════════════════════════════════════════════╝", "38;5;99"))
    print()

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with backend_log.open("w", encoding="utf-8") as blog, \
            frontend_log.open("w", encoding="utf-8") as flog:
        engine = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000"],
            cwd=str(BACKEND), stdout=blog, stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        webapp = subprocess.Popen(
            "npm run dev", cwd=str(FRONTEND), shell=True,
            stdout=flog, stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

        print(c("  Starting the engine and web app…", "37"))
        engine_up = webapp_up = False
        opened = False
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if engine.poll() is not None:
                print(c("\n  ✘ The engine failed to start:\n", "91"))
                print(tail(backend_log))
                return 1
            if webapp.poll() is not None:
                print(c("\n  ✘ The web app failed to start:\n", "91"))
                print(tail(frontend_log))
                return 1
            if not engine_up and api_ok():
                engine_up = True
                print(c("  ✔ Engine ready", "92"))
            if not webapp_up and http_ok(WEB):
                webapp_up = True
                print(c("  ✔ Web app ready", "92"))
            if engine_up and webapp_up and not opened:
                opened = True
                print(c(f"\n  Open in your browser:  {WEB}\n", "96"))
                if os.name == "nt":
                    os.system(f"start {WEB}")
                break
            time.sleep(0.6)

        if not (engine_up and webapp_up):
            print(c("\n  ✘ Timed out waiting for ClipForge to come up.", "91"))
            print(c("  engine log:", "90"))
            print(tail(backend_log))
            return 1

        _progress_loop(engine, webapp, backend_log, frontend_log)
    return 0


def _progress_loop(engine, webapp, backend_log, frontend_log) -> None:
    samples: deque = deque()
    current = None
    announced = set()

    while True:
        # If a child dies, surface it and stop — the job will clean up the rest.
        if engine.poll() is not None:
            write_line("")
            print(c("\n  ✘ The engine stopped unexpectedly:\n", "91"))
            print(tail(backend_log))
            return
        if webapp.poll() is not None:
            write_line("")
            print(c("\n  ✘ The web app stopped unexpectedly:\n", "91"))
            print(tail(frontend_log))
            return

        try:
            with urllib.request.urlopen(f"{API}/api/jobs?limit=5", timeout=4) as r:
                jobs = json.loads(r.read())
        except Exception:  # noqa: BLE001
            write_line(c("  …", "90"))
            time.sleep(2)
            continue

        active = next((j for j in jobs if j["status"] in ("running", "queued")), None)
        if active is None:
            latest = jobs[0] if jobs else None
            if latest and latest["id"] not in announced and latest["status"] in (
                "done", "error", "cancelled"
            ):
                announced.add(latest["id"])
                s, f = parse_time(latest.get("started_at")), parse_time(latest.get("finished_at"))
                took = f" in {fmt_span((f - s).total_seconds())}" if s and f else ""
                icon = {"done": ("✔", "92"), "error": ("✘", "91"), "cancelled": ("⊘", "90")}[latest["status"]]
                write_line("")
                print(c(f"\r  {icon[0]} {latest['status']}{took}", icon[1]))
            write_line(c("  ● ready — upload a video in your browser to begin", "90"))
            current = None
            samples.clear()
            time.sleep(2)
            continue

        if active["id"] != current:
            current = active["id"]
            samples.clear()
            write_line("")
            print(c(f"\r  ▶ working on a new job…", "96"))

        progress = float(active.get("progress", 0.0))
        now = time.monotonic()
        samples.append((now, progress))
        while samples and now - samples[0][0] > 90:
            samples.popleft()

        eta = "estimating…"
        if len(samples) >= 2:
            dt = samples[-1][0] - samples[0][0]
            dp = samples[-1][1] - samples[0][1]
            if dt > 8 and dp > 0.3:
                eta = f"~{fmt_span((100 - progress) / (dp / dt))} left"
            elif dt > 30:
                eta = "working…"

        started = parse_time(active.get("started_at"))
        elapsed = fmt_span((datetime.now(timezone.utc) - started).total_seconds()) if started else "0:00"
        filled = int(BAR * min(max(progress, 0), 100) / 100)
        bar = c("█" * filled, "38;5;99") + c("░" * (BAR - filled), "90")
        msg = active.get("message") or "starting"
        write_line(f"  {bar} {progress:5.1f}%  {elapsed} · {eta}  │ {msg}")
        time.sleep(2)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(c("\n\n  Stopping ClipForge… bye 👋", "90"))
        sys.exit(0)

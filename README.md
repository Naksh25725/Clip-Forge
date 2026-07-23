<div align="center">

# 🎬 ClipForge

**Split any video into shareable clips — with AI picking the best moments.**

Upload a video (or paste a Google Drive link), and ClipForge turns it into
parts for YouTube Shorts, Instagram Reels and TikTok: the whole thing in equal
pieces, or just the **most viral-worthy moments**, rated 0–100 by AI.

*Self-hosted · Free · MIT licensed · No watermarks · No account*

</div>

---

## What it does

One page, three questions:

**1 — Where's the video?** Drag & drop a file, or paste a Google Drive link and
ClipForge downloads it for you.

**2 — What do you want out of it?**

- 🔥 **Best clips only** — finds the strongest moments and scores each one
  **0–100 for viral potential**, with a written reason. Ask for "5 clips of ~45s"
  from a 10-minute video and you get the 5 best, ranked and explained.
- **Equal parts** — split the whole thing into N parts.
- **Fixed length** — a new part every N seconds.

Then choose the **output format** — keep the original shape, or make a **9:16
reel** (fill-the-screen crop, or the whole frame over a blurred background).
Add text overlays and **drag them into place on a live preview** of your video.

**3 — Where do the clips go?** A folder on your computer, Google Drive, or kept
in the app to download individually.

## How the AI works

Everything runs on **Groq's free tier** plus **Whisper** — no paid services.

- **Transcription** turns speech into timestamped text. Two engines, switchable
  per run: **Groq cloud** (Whisper large-v3-turbo — a 40-min video in seconds)
  or **local** (`faster-whisper` on your machine — private, offline). Cloud
  falls back to local automatically if it's unavailable.
- **Clip rating** feeds the transcript to Groq's LLM, which scores each moment
  on hook strength, payoff and emotional charge — blended with audio energy and
  on-screen motion.

No keys at all? It still works: clips are scored on audio energy and visual cut
density, and every clip tells you which method rated it.

## Tech stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 15 · React 19 · TypeScript · Tailwind · Framer Motion · SWR |
| Backend | FastAPI · SQLAlchemy 2 (async) · SQLite · FFmpeg · faster-whisper |
| AI | Groq free tier (LLM rating + cloud Whisper) — all optional |
| Infra | Docker · Docker Compose |

---

## Run it (Windows, no Docker)

Requirements: **Python 3.11+**, **Node 20+**, **FFmpeg** on your PATH.

```bat
:: one-time setup
cd backend && pip install -r requirements.txt && cd ..
cd frontend && npm install && cd ..

:: every time — opens the engine, the web app, and a live progress window
start.bat
```

One window opens showing live progress, and a browser tab opens at
**http://localhost:3000**. That single window runs everything — **close it (or
press Ctrl+C) to stop ClipForge completely.** Nothing is left running.

## Run it (Docker, any OS)

```bash
cp .env.example .env      # optional — defaults work out of the box
docker compose up --build
```

- Web app → http://localhost:3000
- API docs → http://localhost:8000/docs

## Optional keys (`.env`)

Everything below is optional — ClipForge runs with none of it.

| Variable | Unlocks |
|----------|---------|
| `GROQ_API_KEY` | AI clip rating + fast cloud transcription ([free key](https://console.groq.com/keys)) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Importing private Drive links & saving clips to Drive |

Local transcription needs `faster-whisper` (in `requirements.txt`); the first
run downloads a ~150 MB model. See [`.env.example`](.env.example) for the full,
annotated list.

### Google Drive (optional)

1. In [Google Cloud Console](https://console.cloud.google.com): enable the
   **Drive API**, configure the OAuth consent screen, create an **OAuth Client
   ID** (type *Web application*).
2. Add `http://localhost:8000/api/drive/callback` as an authorized redirect URI.
3. Put the client ID/secret in `.env`, restart, then connect from the output
   step. Public "anyone with the link" videos import without any of this.

---

## How it's built

```
backend/app/
├── main.py            FastAPI app, CORS, /media static, startup
├── config.py          settings from .env (root or backend/)
├── models.py          Video · Job · Part · Setting
├── schemas.py         request/response models
├── api/               videos · jobs · parts · settings · drive
├── services/
│   ├── ffmpeg.py          cut, thumbnail, 9:16 reel geometry, text burn-in
│   ├── transcription.py   local faster-whisper
│   ├── cloud_stt.py       Groq cloud Whisper (chunked, timestamp-stitched)
│   ├── viral.py           moment finding + 3-tier scoring
│   ├── ai.py              Groq LLM: clip rating + titles
│   ├── downloader.py      Google Drive / direct link download
│   ├── drive.py           OAuth, folder listing, upload
│   └── export.py          deliver parts to a folder or Drive
└── workers/
    ├── queue.py           persistent in-process job queue
    └── pipeline.py        segment → transcribe → rate → render → export

frontend/src/
├── app/page.tsx       the single dashboard (three steps + results)
├── components/        source · split · output · reel-preview · part-card
├── services/          typed API client
└── types/             shared models
```

**Pipeline:** plan segments (or find best moments) → transcribe once →
rate/name with Groq → render each part with FFmpeg (reel transform + burned-in
text) → export. Jobs are persisted, so they survive a restart.

## License

[MIT](LICENSE) — do whatever you want. Contributions welcome; see
[CONTRIBUTING.md](CONTRIBUTING.md).

# Contributing to ClipForge

Thanks for wanting to make ClipForge better! Bug reports, docs fixes and
features are all welcome.

## Getting started

1. Fork and clone the repo.
2. Follow **Local development** in the README to run the backend and frontend.
3. Branch off: `git checkout -b feat/my-feature` (or `fix/…`, `docs/…`).

## Guidelines

### Backend (FastAPI, Python 3.11+)

- Routes stay thin — the real work lives in `app/services` and `app/workers`.
- Everything is async; wrap sync libraries (Whisper, the Google client,
  `shutil`) with `asyncio.to_thread`.
- New config goes through `app/config.py` with a sensible default plus an entry
  in `.env.example`.
- Anything optional (Groq, Drive, Whisper) must degrade gracefully when it isn't
  configured — never crash a run because a key is missing.

### Frontend (Next.js 15, TypeScript)

- It's deliberately **one page** (`src/app/page.tsx`) with four panels. Please
  don't add routes without a good reason.
- Strict TypeScript — avoid `any`.
- API calls go through `src/services`, which wraps `lib/api.ts`.
- Run `npm run typecheck` before pushing.

> Don't run `npm run build` while `npm run dev` is running — they share `.next`
> and the dev server's cache gets corrupted. Stop one first.

## Commits & PRs

- Imperative commit messages ("Add label position option").
- One logical change per PR; screenshots for UI changes.
- Fill in the PR template, especially **how you tested it**.

## Reporting bugs

Use the bug report template. Backend logs (the `uvicorn` output) and the browser
console are usually the fastest route to a fix.

## Code of conduct

Be kind, assume good intent. Harassment of any kind isn't tolerated.

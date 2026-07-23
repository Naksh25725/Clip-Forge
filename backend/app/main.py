import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .config import get_settings
from .database import init_db
from .services.ffmpeg import resolve_font
from .workers import queue

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s — %(message)s"
)
logger = logging.getLogger("clipforge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    await init_db()
    await queue.start_workers()
    if not resolve_font():
        logger.warning("No TrueType font found — part labels will not be burned in. "
                       "Set CLIPFORGE_FONT_FILE to a .ttf path.")
    logger.info("ClipForge ready — data dir: %s", settings.data_dir.resolve())
    yield
    await queue.stop_workers()


app = FastAPI(
    title="ClipForge API",
    description="Split a video into labelled parts.",
    version="2.0.0",
    lifespan=lifespan,
)

settings = get_settings()
settings.ensure_dirs()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Thumbnails and rendered parts (StaticFiles supports HTTP range for <video>).
app.mount("/media", StaticFiles(directory=settings.data_dir), name="media")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}

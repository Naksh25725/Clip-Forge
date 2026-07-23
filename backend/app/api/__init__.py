from fastapi import APIRouter

from . import drive, jobs, parts, settings, videos

api_router = APIRouter(prefix="/api")
api_router.include_router(videos.router)
api_router.include_router(jobs.router)
api_router.include_router(parts.router)
api_router.include_router(settings.router)
api_router.include_router(drive.router)

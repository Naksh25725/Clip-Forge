from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import Job, Video
from ..schemas import JobCreate, JobDetail, JobOut
from ..services.export import ExportError, validate_local_dir
from ..workers import queue

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobDetail, status_code=201)
async def create_job(payload: JobCreate, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, payload.video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    if video.status != "ready":
        raise HTTPException(409, f"Video is not ready yet (status: {video.status})")

    options = payload.options
    # Fail fast on a bad destination rather than after rendering everything.
    if options.output_mode == "local":
        try:
            validate_local_dir(options.output_dir)
        except ExportError as exc:
            raise HTTPException(400, str(exc)) from exc

    job = Job(video_id=video.id, options=options.model_dump(), status="queued")
    db.add(job)
    await db.commit()
    await queue.enqueue(job.id)

    result = await db.execute(
        select(Job)
        .where(Job.id == job.id)
        .options(selectinload(Job.video), selectinload(Job.parts))
    )
    return result.scalar_one()


@router.get("", response_model=list[JobOut])
async def list_jobs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job).order_by(Job.created_at.desc()).limit(min(limit, 100))
    )
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.video), selectinload(Job.parts))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    job.parts.sort(key=lambda p: p.index)
    return job


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status in ("done", "error", "cancelled"):
        raise HTTPException(409, f"Job is already {job.status}")
    queue.request_cancel(job_id)
    if job.status == "queued":
        job.status = "cancelled"
        await db.commit()
        await db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)) -> None:
    from pathlib import Path

    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    result = await db.execute(
        select(Job).where(Job.id == job_id).options(selectinload(Job.parts))
    )
    full = result.scalar_one()
    for part in full.parts:
        if part.path:
            Path(part.path).unlink(missing_ok=True)
        if part.thumbnail_path:
            Path(part.thumbnail_path).unlink(missing_ok=True)
    await db.delete(job)
    await db.commit()

"""In-process job queue. Jobs are persisted, so they survive a restart."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from ..database import SessionLocal
from ..models import Job

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[str] = asyncio.Queue()
_workers: list[asyncio.Task] = []
_cancelled: set[str] = set()

WORKER_COUNT = 1  # video encoding is CPU-bound; one at a time keeps it predictable


def request_cancel(job_id: str) -> None:
    _cancelled.add(job_id)


def is_cancelled(job_id: str) -> bool:
    return job_id in _cancelled


async def enqueue(job_id: str) -> None:
    await _queue.put(job_id)


async def _run_job(job_id: str) -> None:
    from .pipeline import run_split_job

    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job is None or job.status in ("done", "cancelled"):
            return
        if is_cancelled(job_id):
            job.status = "cancelled"
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    try:
        await run_split_job(job_id)
        async with SessionLocal() as db:
            job = await db.get(Job, job_id)
            if job and job.status == "running":
                cancelled = is_cancelled(job_id)
                job.status = "cancelled" if cancelled else "done"
                if not cancelled:
                    job.progress = 100.0
                    job.message = "Finished"
                job.finished_at = datetime.now(timezone.utc)
                await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s failed", job_id)
        async with SessionLocal() as db:
            job = await db.get(Job, job_id)
            if job:
                job.status = "error"
                job.error = str(exc)[:2000]
                job.finished_at = datetime.now(timezone.utc)
                await db.commit()
    finally:
        _cancelled.discard(job_id)


async def _worker_loop(index: int) -> None:
    logger.info("Worker %d ready", index)
    while True:
        job_id = await _queue.get()
        try:
            await _run_job(job_id)
        finally:
            _queue.task_done()


async def start_workers() -> None:
    async with SessionLocal() as db:
        result = await db.execute(select(Job).where(Job.status.in_(["queued", "running"])))
        for job in result.scalars():
            job.status = "queued"
            await _queue.put(job.id)
        await db.commit()

    for i in range(WORKER_COUNT):
        _workers.append(asyncio.create_task(_worker_loop(i)))


async def stop_workers() -> None:
    for task in _workers:
        task.cancel()
    _workers.clear()

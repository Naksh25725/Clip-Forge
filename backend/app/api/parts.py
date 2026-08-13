import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Part
from ..schemas import ExportRequest, PartOut, PartUpdate
from ..services.export import ExportError, safe_filename, validate_local_dir
from ..workers.pipeline import export_one_part, render_one_part

router = APIRouter(prefix="/parts", tags=["parts"])


async def _get_part(part_id: str, db: AsyncSession) -> Part:
    part = await db.get(Part, part_id)
    if not part:
        raise HTTPException(404, "Part not found")
    return part


@router.get("", response_model=list[PartOut])
async def list_parts(job_id: str = "", db: AsyncSession = Depends(get_db)):
    stmt = select(Part)
    if job_id:
        stmt = stmt.where(Part.job_id == job_id)
    result = await db.execute(stmt.order_by(Part.index))
    return result.scalars().all()


@router.patch("/{part_id}", response_model=PartOut)
async def update_part(
    part_id: str, payload: PartUpdate, db: AsyncSession = Depends(get_db)
):
    """Rename a part. Changing `label` or `overlays` re-renders it."""
    part = await _get_part(part_id, db)

    rerender = False
    if payload.overlays is not None:
        new_overlays = [
            {"text": o.text.strip(), "y": o.y, "size": o.size}
            for o in payload.overlays
            if o.text.strip()
        ]
        if new_overlays != (part.overlays or []):
            part.overlays = new_overlays
            part.label = new_overlays[0]["text"] if new_overlays else ""
            rerender = True
    elif payload.label is not None and payload.label.strip() != part.label:
        # Legacy path: editing the label edits the first overlay's text.
        text = payload.label.strip()
        overlays = list(part.overlays or [])
        if overlays:
            overlays[0] = {**overlays[0], "text": text}
        elif text:
            overlays = [{"text": text, "y": 0.85, "size": "medium"}]
        part.overlays = [o for o in overlays if o.get("text")]
        part.label = text
        rerender = True

    if payload.title is not None:
        part.title = payload.title.strip()
    if rerender:
        part.status = "rendering"
    await db.commit()
    await db.refresh(part)

    if rerender:
        asyncio.create_task(render_one_part(part_id))
    return part


@router.get("/{part_id}/download")
async def download_part(part_id: str, db: AsyncSession = Depends(get_db)):
    part = await _get_part(part_id, db)
    if not part.path or not Path(part.path).exists():
        raise HTTPException(404, "This part hasn't been rendered yet")
    src = Path(part.path)
    base = part.title.strip() or part.label.strip() or f"part-{part.index}"
    filename = f"{part.index:02d} - {safe_filename(base)}{src.suffix}"
    return FileResponse(src, filename=filename, media_type="application/octet-stream")


@router.post("/export", status_code=202)
async def export_parts(payload: ExportRequest, db: AsyncSession = Depends(get_db)):
    """Save the given parts to a local folder or upload them to Google Drive."""
    if payload.mode == "local":
        try:
            validate_local_dir(payload.output_dir)
        except ExportError as exc:
            raise HTTPException(400, str(exc)) from exc

    destination = (
        payload.drive_folder_id if payload.mode == "drive" else payload.output_dir
    )
    started = 0
    if payload.part_ids:
        stmt = select(Part).where(Part.id.in_(payload.part_ids))
        result = await db.execute(stmt)
        parts = result.scalars().all()
        for part in parts:
            if part.status == "ready":
                asyncio.create_task(export_one_part(part.id, payload.mode, destination))
                started += 1
    if started == 0:
        raise HTTPException(400, "No rendered parts to export")
    return {"started": started}


@router.delete("/{part_id}", status_code=204)
async def delete_part(part_id: str, db: AsyncSession = Depends(get_db)) -> None:
    part = await _get_part(part_id, db)
    if part.path:
        Path(part.path).unlink(missing_ok=True)
    if part.thumbnail_path:
        Path(part.thumbnail_path).unlink(missing_ok=True)
    await db.delete(part)
    await db.commit()

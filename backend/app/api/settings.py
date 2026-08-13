from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db
from ..models import Setting
from ..schemas import (
    AiStatus,
    AppSettings,
    AppSettingsUpdate,
    FolderCheck,
    FolderCheckResult,
)
from ..services import ai
from ..services.export import ExportError, validate_local_dir

router = APIRouter(tags=["settings"])


async def _load(db: AsyncSession) -> AppSettings:
    result = await db.execute(select(Setting))
    stored = {row.key: row.value for row in result.scalars()}
    defaults = AppSettings().model_dump()
    if not stored.get("output_dir"):
        stored["output_dir"] = str(get_settings().default_output_dir.resolve())
    merged = {key: stored.get(key) or default for key, default in defaults.items()}
    try:
        return AppSettings(**merged)
    except ValueError:
        return AppSettings(**defaults)


@router.get("/settings", response_model=AppSettings)
async def get_app_settings(db: AsyncSession = Depends(get_db)):
    return await _load(db)


@router.put("/settings", response_model=AppSettings)
async def update_app_settings(
    payload: AppSettingsUpdate, db: AsyncSession = Depends(get_db)
):
    for key, value in payload.model_dump(exclude_none=True).items():
        row = await db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=str(value)))
        else:
            row.value = str(value)
    await db.commit()
    return await _load(db)


@router.post("/settings/check-folder", response_model=FolderCheckResult)
async def check_folder(payload: FolderCheck):
    """Confirm an output folder exists (creating it if needed) before a run."""
    try:
        resolved = validate_local_dir(payload.path)
    except ExportError as exc:
        return FolderCheckResult(ok=False, message=str(exc))
    return FolderCheckResult(
        ok=True, resolved=str(resolved.resolve()), message="Folder is ready"
    )


@router.get("/ai/status", response_model=AiStatus)
async def ai_status():
    from ..services import cloud_stt
    from ..services.transcription import whisper_available

    ok, message = await ai.check_key()
    return AiStatus(
        has_key=ai.has_key(),
        model=get_settings().groq_model,
        stt_model=get_settings().groq_stt_model,
        ok=ok,
        message=message,
        whisper_available=whisper_available(),
        cloud_stt_available=cloud_stt.available(),
    )

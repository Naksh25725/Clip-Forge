import asyncio
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from ..config import get_settings
from ..schemas import CreateFolderRequest, DriveFolder, DriveStatus
from ..services import drive

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/drive", tags=["drive"])


def _frontend_url() -> str:
    origins = get_settings().cors_origin_list
    return origins[0] if origins else "http://localhost:3000"


@router.get("/status", response_model=DriveStatus)
async def status():
    configured = drive.is_configured()
    connected = configured and drive.is_connected()
    return DriveStatus(
        configured=configured,
        connected=connected,
        account_email=await drive.account_email() if connected else "",
    )


@router.get("/auth-url")
async def auth_url():
    if not drive.is_configured():
        raise HTTPException(
            409,
            "Google Drive isn't configured. Add GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET to your .env, then restart the backend.",
        )
    return {"url": await asyncio.to_thread(drive.get_auth_url)}


@router.get("/callback")
async def oauth_callback(code: str = "", error: str = ""):
    if error or not code:
        return RedirectResponse(f"{_frontend_url()}/?drive=error")
    try:
        await asyncio.to_thread(drive.exchange_code, code)
    except Exception:  # noqa: BLE001
        logger.exception("Drive OAuth exchange failed")
        return RedirectResponse(f"{_frontend_url()}/?drive=error")
    return RedirectResponse(f"{_frontend_url()}/?drive=connected")


@router.post("/disconnect", status_code=204)
async def disconnect() -> None:
    drive.disconnect()


@router.get("/folders", response_model=list[DriveFolder])
async def folders():
    if not drive.is_connected():
        raise HTTPException(401, "Google Drive isn't connected")
    try:
        return await drive.list_folders()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Drive API error: {exc}") from exc


@router.post("/folders", response_model=DriveFolder, status_code=201)
async def create_folder(payload: CreateFolderRequest):
    if not drive.is_connected():
        raise HTTPException(401, "Google Drive isn't connected")
    try:
        return await drive.create_folder(payload.name, payload.parent)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Drive API error: {exc}") from exc

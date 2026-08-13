"""Google Drive: OAuth, folder listing, downloads and resumable uploads.

The google-* client libraries are synchronous, so every call runs in a thread.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path

from ..config import get_secrets, get_settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _token_path() -> Path:
    return get_settings().credentials_dir / "google_token.json"


def is_configured() -> bool:
    s = get_secrets()
    return bool(s.google_client_id and s.google_client_secret)


def is_connected() -> bool:
    return _token_path().exists()


try:
    from google.auth.exceptions import GoogleAuthError
    from googleapiclient.errors import Error as ApiError

    DRIVE_EXCEPTIONS = (ApiError, GoogleAuthError, ImportError, ValueError, OSError)
except ImportError:
    DRIVE_EXCEPTIONS = (ImportError, ValueError, OSError)


def _client_config() -> dict:
    s = get_secrets()
    return {
        "web": {
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [s.google_redirect_uri],
        }
    }


def _build_flow():
    from google_auth_oauthlib.flow import Flow

    return Flow.from_client_config(
        _client_config(), scopes=SCOPES, redirect_uri=get_secrets().google_redirect_uri
    )


def get_auth_url() -> str:
    url, _state = _build_flow().authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    return url


def exchange_code(code: str) -> None:
    flow = _build_flow()
    flow.fetch_token(code=code)
    _token_path().parent.mkdir(parents=True, exist_ok=True)
    _token_path().write_text(flow.credentials.to_json(), encoding="utf-8")


def disconnect() -> None:
    _token_path().unlink(missing_ok=True)


def _load_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_info(
        json.loads(_token_path().read_text(encoding="utf-8")), SCOPES
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _token_path().write_text(creds.to_json(), encoding="utf-8")
    return creds


def _service(name: str = "drive", version: str = "v3"):
    from googleapiclient.discovery import build

    return build(name, version, credentials=_load_credentials(), cache_discovery=False)


def _account_email_sync() -> str:
    try:
        return _service("oauth2", "v2").userinfo().get().execute().get("email", "")
    except Exception:  # noqa: BLE001
        return ""


async def account_email() -> str:
    if not is_connected():
        return ""
    return await asyncio.to_thread(_account_email_sync)


def _list_folders_sync() -> list[dict]:
    result = (
        _service()
        .files()
        .list(
            q="mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id,name)",
            pageSize=200,
            orderBy="name",
        )
        .execute()
    )
    return [{"id": f["id"], "name": f["name"]} for f in result.get("files", [])]


async def list_folders() -> list[dict]:
    return await asyncio.to_thread(_list_folders_sync)


def _create_folder_sync(name: str, parent: str = "root") -> dict:
    metadata: dict = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent and parent != "root":
        metadata["parents"] = [parent]
    created = _service().files().create(body=metadata, fields="id,name").execute()
    return {"id": created["id"], "name": created["name"]}


async def create_folder(name: str, parent: str = "root") -> dict:
    return await asyncio.to_thread(_create_folder_sync, name, parent)


# ── Download (for pulling a source video out of Drive) ───────────────────

_EXT_BY_MIME = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
    "video/x-msvideo": ".avi",
    "video/webm": ".webm",
}


def _file_metadata_sync(file_id: str) -> tuple[str, str]:
    meta = _service().files().get(fileId=file_id, fields="name,mimeType").execute()
    name = meta.get("name", f"drive-{file_id}")
    suffix = Path(name).suffix or _EXT_BY_MIME.get(meta.get("mimeType", ""), ".mp4")
    return name, suffix


async def file_metadata(file_id: str) -> tuple[str, str]:
    return await asyncio.to_thread(_file_metadata_sync, file_id)


def _download_sync(
    file_id: str, dest: str, on_progress: Callable[[float], None] | None
) -> None:
    from googleapiclient.http import MediaIoBaseDownload

    request = _service().files().get_media(fileId=file_id)
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as handle:
        downloader = MediaIoBaseDownload(handle, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status and on_progress:
                on_progress(min(status.progress() * 100, 99.0))


async def download_file(
    file_id: str, dest: Path, on_progress: Callable[[float], None] | None = None
) -> None:
    await asyncio.to_thread(_download_sync, file_id, str(dest), on_progress)


# ── Upload (for delivering finished parts) ──────────────────────────────


def _upload_sync(
    path: str, name: str, folder_id: str, on_progress: Callable[[float], None] | None
) -> str:
    from googleapiclient.http import MediaFileUpload

    metadata: dict = {"name": name}
    if folder_id and folder_id != "root":
        metadata["parents"] = [folder_id]
    media = MediaFileUpload(path, resumable=True, chunksize=8 * 1024 * 1024)
    request = _service().files().create(body=metadata, media_body=media, fields="id")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status and on_progress:
            on_progress(status.progress() * 100)
    return response["id"]


async def upload_file(
    path: Path,
    name: str,
    folder_id: str = "root",
    on_progress: Callable[[float], None] | None = None,
) -> str:
    return await asyncio.to_thread(
        _upload_sync, str(path), name, folder_id, on_progress
    )

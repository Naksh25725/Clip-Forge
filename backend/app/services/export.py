"""Deliver finished parts to their destination: a local folder or Google Drive."""

import asyncio
import logging
import re
import shutil
from pathlib import Path

from . import drive
from ..config import get_settings

logger = logging.getLogger(__name__)


class ExportError(RuntimeError):
    pass


def safe_filename(name: str, fallback: str = "part") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120] or fallback


def validate_local_dir(raw: str) -> Path:
    """Resolve and create the user's chosen output folder."""
    if not raw.strip():
        raise ExportError("No output folder set")

    path = Path(raw.strip()).expanduser().resolve()
    base_dir = get_settings().default_output_dir.resolve()

    if not path.is_relative_to(base_dir):
        raise ExportError("Output folder must be within the allowed base directory")

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportError(f"Cannot use that folder: {exc}") from exc
    if not path.is_dir():
        raise ExportError("That path is not a folder")
    return path


async def export_local(src: Path, filename: str, out_dir: str) -> str:
    target_dir = validate_local_dir(out_dir)
    dest = target_dir / filename
    # Never silently overwrite an existing export.
    counter = 2
    while dest.exists():
        dest = target_dir / f"{Path(filename).stem} ({counter}){Path(filename).suffix}"
        counter += 1
    await asyncio.to_thread(shutil.copy2, src, dest)
    return str(dest)


async def export_drive(src: Path, filename: str, folder_id: str) -> str:
    if not drive.is_connected():
        raise ExportError("Google Drive is not connected")
    file_id = await drive.upload_file(src, filename, folder_id or "root")
    return f"https://drive.google.com/file/d/{file_id}/view"


async def export_part(src: Path, filename: str, mode: str, destination: str) -> str:
    """Returns a human-readable location for the exported file."""
    if not src.exists():
        raise ExportError("Rendered file is missing")
    if mode == "drive":
        return await export_drive(src, filename, destination)
    return await export_local(src, filename, destination)

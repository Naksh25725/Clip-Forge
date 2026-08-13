"""Download a source video from a Google Drive link (or any direct URL).

Private Drive files work when the account is connected under Settings; public
"anyone with the link" files download without any credentials at all.
"""

import asyncio
import ipaddress
import logging
import re
import socket
from collections.abc import Callable
from pathlib import Path

import httpx

from . import drive

logger = logging.getLogger(__name__)

_DRIVE_ID_PATTERNS = [
    r"/file/d/([a-zA-Z0-9_-]{10,})",
    r"/d/([a-zA-Z0-9_-]{10,})",
    r"[?&]id=([a-zA-Z0-9_-]{10,})",
]

_FILENAME_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.IGNORECASE)


class DownloadError(RuntimeError):
    pass


def extract_drive_id(url: str) -> str | None:
    for pattern in _DRIVE_ID_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def is_drive_link(url: str) -> bool:
    return "drive.google.com" in url or "docs.google.com" in url


async def _verify_request(request: httpx.Request) -> None:
    hostname = request.url.host
    try:
        loop = asyncio.get_running_loop()
        info = await loop.getaddrinfo(hostname, None)
        for res in info:
            ip_str = res[4][0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
                raise DownloadError(f"Access to restricted IP is denied")
    except socket.gaierror:
        raise DownloadError(f"Could not resolve hostname {hostname}")


async def _stream_to_file(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    dest: Path,
    on_progress: Callable[[float], None] | None,
    **kwargs,
) -> str:
    """Stream a response body to disk. Returns the server-suggested filename."""
    async with client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            raise DownloadError("html")  # caller retries with a confirm token

        total = int(response.headers.get("content-length", 0) or 0)
        suggested = ""
        disposition = response.headers.get("content-disposition", "")
        if match := _FILENAME_RE.search(disposition):
            suggested = match.group(1)

        dest.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with dest.open("wb") as f:
            async for chunk in response.aiter_bytes(1024 * 1024):
                f.write(chunk)
                written += len(chunk)
                if on_progress and total:
                    on_progress(min(written / total * 100, 99.0))
        if written == 0:
            raise DownloadError("Downloaded 0 bytes")
        return suggested


async def _download_public_drive(
    file_id: str, dest: Path, on_progress: Callable[[float], None] | None
) -> str:
    """Public Drive download, handling the large-file virus-scan interstitial."""
    url = "https://drive.usercontent.google.com/download"
    params = {"id": file_id, "export": "download", "confirm": "t"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
        try:
            return await _stream_to_file(client, "GET", url, dest, on_progress, params=params)
        except DownloadError as exc:
            if str(exc) != "html":
                raise
        # Interstitial returned — replay the confirmation form it contains.
        page = (await client.get(url, params=params)).text
        form_params = dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', page))
        if not form_params:
            raise DownloadError(
                "Google returned a confirmation page. Make sure the link is shared "
                "with 'Anyone with the link', or connect your Google account."
            )
        form_params.setdefault("id", file_id)
        form_params["confirm"] = "t"
        return await _stream_to_file(
            client, "GET", url, dest, on_progress, params=form_params
        )


async def download(
    url: str, dest_dir: Path, video_id: str, on_progress: Callable[[float], None] | None = None
) -> tuple[Path, str]:
    """Fetch `url` into `dest_dir`. Returns (path, display name)."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise DownloadError("Enter a full http(s) link")

    if is_drive_link(url):
        file_id = extract_drive_id(url)
        if not file_id:
            raise DownloadError("Could not find a file id in that Google Drive link")

        # Private files need the connected account; public ones do not.
        if drive.is_connected():
            try:
                name, suffix = await drive.file_metadata(file_id)
                dest = dest_dir / f"{video_id}{suffix}"
                await drive.download_file(file_id, dest, on_progress)
                return dest, name
            except Exception:  # noqa: BLE001 — fall back to the public path
                logger.warning("Drive API download failed; trying public link", exc_info=True)

        dest = dest_dir / f"{video_id}.mp4"
        suggested = await _download_public_drive(file_id, dest, on_progress)
        name = suggested or f"drive-{file_id}.mp4"
        if suffix := Path(name).suffix:
            renamed = dest.with_suffix(suffix)
            if renamed != dest:
                dest.replace(renamed)
                dest = renamed
        return dest, name

    # Any other direct link
    name = Path(httpx.URL(url).path).name or "video.mp4"
    dest = dest_dir / f"{video_id}{Path(name).suffix or '.mp4'}"
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=None, event_hooks={"request": [_verify_request]}
    ) as client:
        suggested = await _stream_to_file(client, "GET", url, dest, on_progress)
    return dest, suggested or name

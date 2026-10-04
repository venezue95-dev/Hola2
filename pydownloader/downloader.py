from __future__ import annotations

import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from . import googledrive, mediafire, youtube
from .utils import createID, get_url_file_name, req_file_size, slugify
from .url_policy import UrlPolicyError, validate_public_url


class Downloader:
    """Descargador común para URLs públicas que entrega un archivo local."""

    def __init__(self, destpath: str = "", timeout=(20, 120), max_retries: int = 3):
        self.filename = ""
        self.stoping = False
        self.destpath = destpath or ""
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.max_bytes = int(os.getenv("MAX_DOWNLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))
        self.id = createID(12)
        self.url = ""
        self.progressfunc = None
        self.args = None
        if self.destpath:
            Path(self.destpath).mkdir(parents=True, exist_ok=True)
            if not self.destpath.endswith(os.sep):
                self.destpath += os.sep

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "UploadET/2.0 (+public-file-downloader)",
            "Accept": "*/*",
        })

    def download_url(self, url="", progressfunc=None, args=None):
        self.url = (url or "").strip()
        self.progressfunc = progressfunc
        self.args = args
        self.stoping = False

        try:
            self.url = validate_public_url(self.url)
        except UrlPolicyError:
            return None
        parsed = urlparse(self.url)

        resolved_url = self.url
        try:
            host = parsed.netloc.lower().split(":", 1)[0]
            if host == "youtube.com" or host.endswith(".youtube.com") or host == "youtu.be":
                data = youtube.getVideoData(self.url)
                if not data:
                    return None
                resolved_url = data["url"]
                self.filename = _safe_filename(data.get("name") or "video")
            elif host == "mediafire.com" or host.endswith(".mediafire.com"):
                resolved_url = mediafire.get(self.url)
            elif host == "drive.google.com" or host.endswith(".drive.google.com") or host == "docs.google.com":
                info = googledrive.get_info(self.url)
                resolved_url = info["file_url"]
                self.filename = _safe_filename(info.get("file_name") or "archivo")
        except Exception:
            return None

        try:
            validate_public_url(resolved_url)
        except UrlPolicyError:
            return None

        for attempt in range(self.max_retries):
            if self.stoping:
                return None
            try:
                response = self._get_with_safe_redirects(resolved_url)
                if response.status_code in {408, 425, 429, 500, 502, 503, 504}:
                    response.close()
                    raise requests.HTTPError(f"HTTP {response.status_code}")
                if not response.ok:
                    response.close()
                    return None
                return self._process_download(response.url, response, progressfunc, args)
            except (requests.RequestException, OSError):
                if attempt + 1 >= self.max_retries:
                    return None
                time.sleep(min(2 ** attempt, 8))
        return None

    def _get_with_safe_redirects(self, url: str, max_redirects: int = 6):
        current = url
        for _ in range(max_redirects + 1):
            validate_public_url(current)
            response = self.session.get(
                current,
                allow_redirects=False,
                stream=True,
                timeout=self.timeout,
            )
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise requests.RequestException("Redirección sin destino")
                current = validate_public_url(urljoin(current, location))
                continue
            return response
        raise requests.TooManyRedirects("Demasiadas redirecciones")

    def _process_download(self, url, response, progressfunc=None, args=None):
        filename = self.filename or _safe_filename(get_url_file_name(url, response) or "archivo_descargado")
        self.filename = filename
        destination = os.path.join(self.destpath, filename)
        total = req_file_size(response)
        if total > self.max_bytes:
            response.close()
            return None
        downloaded = 0
        started = time.monotonic()
        last_report = started
        last_bytes = 0

        try:
            with response, open(destination, "wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if self.stoping:
                        return None
                    if not chunk:
                        continue
                    output.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > self.max_bytes:
                        raise OSError("El archivo supera MAX_DOWNLOAD_BYTES")
                    now = time.monotonic()
                    if progressfunc and (now - last_report >= 0.8 or (total and downloaded >= total)):
                        elapsed = max(now - started, 0.001)
                        speed = int((downloaded - last_bytes) / max(now - last_report, 0.001))
                        remaining = max((total - downloaded) / max(downloaded / elapsed, 1), 0) if total else 0
                        progressfunc(self, filename, downloaded, total, speed, remaining, args)
                        last_report = now
                        last_bytes = downloaded
                output.flush()
            return destination
        except Exception:
            try:
                os.remove(destination)
            except OSError:
                pass
            return None

    def stop(self):
        self.stoping = True

    def renove(self):
        return self.download_url(self.url, self.progressfunc, self.args)


def _safe_filename(value: str) -> str:
    value = str(value or "archivo_descargado").strip()
    value = value.replace("\\", "/").rsplit("/", 1)[-1]
    value = re.sub(r"[\x00-\x1f<>:\"|?*]", "_", value)
    value = value.strip(" .") or "archivo_descargado"
    if value in {".", ".."}:
        value = "archivo_descargado"
    # Conserva extensión y normaliza solo nombres problemáticos.
    return slugify(value, allow_unicode=True) if not re.fullmatch(r"[\w .()\-]+", value, re.UNICODE) else value

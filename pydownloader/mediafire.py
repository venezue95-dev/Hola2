from __future__ import annotations

from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


class MediaFireError(Exception):
    pass


def get(url: str) -> str:
    parsed = urlparse((url or "").strip())
    host = parsed.netloc.lower().split(":", 1)[0]
    if not host.endswith("mediafire.com"):
        raise MediaFireError("La URL no pertenece a MediaFire.")

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or parts[0].lower() not in {"file", "view"}:
        raise MediaFireError("No parece una página pública de archivo de MediaFire.")

    with requests.Session() as session:
        session.headers.update({"User-Agent": "UploadET/2.0"})
        response = session.get(
            f"https://{host}{parsed.path}",
            timeout=(20, 30),
            allow_redirects=True,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        button = soup.select_one("a#downloadButton[href]")
        if not button:
            raise MediaFireError("MediaFire no mostró un enlace directo público.")
        return button["href"]

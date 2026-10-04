from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup


FILE_ID_RE = re.compile(r"[A-Za-z0-9_-]{10,}")


def extract_file_id(url: str) -> str:
    parsed = urlparse((url or "").strip())
    query_id = parse_qs(parsed.query).get("id", [None])[0]
    candidates = [query_id]
    candidates.extend(parsed.path.split("/"))
    for candidate in candidates:
        if candidate and FILE_ID_RE.fullmatch(candidate):
            return candidate
    raise ValueError("No se encontró un ID de archivo de Google Drive.")


def get_direct_url(file_id: str, session=None) -> str | None:
    own_session = session is None
    session = session or requests.Session()
    try:
        response = session.get(
            "https://drive.usercontent.google.com/download",
            params={"export": "download", "id": file_id, "confirm": "t"},
            stream=True,
            allow_redirects=True,
            timeout=(20, 60),
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type.lower():
            final_url = response.url
            response.close()
            return final_url

        token = get_confirm_token(response)
        response.close()
        if not token:
            return None
        response = session.get(
            "https://drive.usercontent.google.com/download",
            params={"export": "download", "id": file_id, "confirm": token},
            stream=True,
            allow_redirects=True,
            timeout=(20, 60),
        )
        response.raise_for_status()
        final_url = response.url
        response.close()
        return final_url
    finally:
        if own_session:
            session.close()


def get_confirm_token(response):
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            return value
    match = re.search(r"confirm=([0-9A-Za-z_\-]+)", response.text or "")
    return match.group(1) if match else None


def get_info(url: str):
    file_id = extract_file_id(url)
    with requests.Session() as session:
        session.headers.update({"User-Agent": "UploadET/2.0"})
        response = session.get(
            f"https://drive.google.com/file/d/{file_id}/view",
            timeout=(20, 30),
            allow_redirects=True,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.find("meta", {"property": "og:title"})
        file_name = title.get("content") if title else f"archivo_{file_id}"
        file_url = get_direct_url(file_id, session=session)
        if not file_url:
            raise ValueError("Google Drive no permite descargar este archivo públicamente.")
        return {"file_name": file_name, "file_id": file_id, "file_url": file_url}

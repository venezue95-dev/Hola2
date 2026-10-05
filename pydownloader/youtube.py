from __future__ import annotations

import os

from .url_policy import UrlPolicyError, validate_public_url

try:
    import yt_dlp
except ImportError:  # Permite que el bot arranque aunque falte el extra opcional.
    yt_dlp = None

LAST_ERROR = ""


def get_video_info(url: str):
    global LAST_ERROR
    LAST_ERROR = ""
    if yt_dlp is None:
        LAST_ERROR = "yt-dlp no está instalado"
        return None

    raw_hosts = os.getenv(
        "YTDLP_ALLOWED_HOSTS",
        "youtube.com,youtu.be,vimeo.com,dailymotion.com,tiktok.com,instagram.com,x.com,twitter.com,facebook.com,twitch.tv,soundcloud.com,bandcamp.com,reddit.com",
    )
    allowed_hosts = [x.strip().lower() for x in raw_hosts.split(",") if x.strip()]
    try:
        safe_url = validate_public_url(url, allowed_hosts=allowed_hosts)
    except UrlPolicyError as exc:
        LAST_ERROR = str(exc)
        return None

    base_options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        # No forzamos un filtro de formato aquí: algunos clientes de YouTube
        # exponen formatos separados y el selector se hace más abajo.
    }
    errors = []
    # YouTube cambia con frecuencia los clientes que permiten extracción sin
    # sesión. Se prueban alternativas públicas sin cookies ni credenciales.
    clients = ["tv_embedded", "web_safari", None]
    for client in clients:
        options = dict(base_options)
        if client:
            options["extractor_args"] = {"youtube": {"player_client": [client]}}
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(safe_url, download=False)
            if info and (info.get("url") or info.get("formats")):
                return info
        except Exception as exc:
            errors.append(f"{client or 'default'}: {exc}")
    LAST_ERROR = errors[-1] if errors else "yt-dlp no devolvió formatos"
    return None


def getVideoData(url: str):
    info = get_video_info(url)
    if not info:
        return None

    formats = [
        f for f in info.get("formats", [])
        if f.get("url") and f.get("vcodec") != "none"
    ]
    # Preferimos un formato progresivo con audio para no depender de ffmpeg
    # durante la descarga. Si no existe, usamos el mejor stream de vídeo.
    combined = [f for f in formats if f.get("acodec") != "none"]
    candidates = combined or formats
    candidates.sort(
        key=lambda f: (
            f.get("height") or 0,
            f.get("tbr") or 0,
            f.get("filesize") or f.get("filesize_approx") or 0,
        ),
        reverse=True,
    )
    selected = candidates[0] if candidates else info
    direct_url = selected.get("url")
    if not direct_url:
        return None

    title = info.get("title") or "video"
    ext = selected.get("ext") or info.get("ext") or "mp4"
    allowed_headers = {}
    for key in ("User-Agent", "Referer", "Origin", "Accept-Language"):
        value = (selected.get("http_headers") or info.get("http_headers") or {}).get(key)
        if value:
            allowed_headers[key] = value
    return {
        "name": f"{title}.{ext}",
        "url": direct_url,
        "headers": allowed_headers,
        "filesize": selected.get("filesize") or selected.get("filesize_approx") or 0,
    }


def get_youtube_info(url):
    return get_video_info(url)


def filter_formats(formats):
    return [f for f in formats if f.get("url") and f.get("vcodec") != "none"]

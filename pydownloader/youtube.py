from __future__ import annotations

import os
from urllib.parse import urlparse

from .url_policy import UrlPolicyError, validate_public_url

try:
    import yt_dlp
except ImportError:  # Permite que el bot arranque aunque falte el extra opcional.
    yt_dlp = None


def get_video_info(url: str):
    if yt_dlp is None:
        return None
    raw_hosts = os.getenv(
        "YTDLP_ALLOWED_HOSTS",
        "youtube.com,youtu.be,vimeo.com,dailymotion.com,tiktok.com,instagram.com,x.com,twitter.com,facebook.com,twitch.tv,soundcloud.com,bandcamp.com,reddit.com",
    )
    allowed_hosts = [x.strip().lower() for x in raw_hosts.split(",") if x.strip()]
    try:
        safe_url = validate_public_url(url, allowed_hosts=allowed_hosts)
    except UrlPolicyError:
        return None
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "format": "best[protocol=https]/best[protocol=http]/best",
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(safe_url, download=False)
    except Exception:
        return None


def getVideoData(url: str):
    info = get_video_info(url)
    if not info:
        return None
    direct_url = info.get("url")
    if not direct_url:
        formats = [f for f in info.get("formats", []) if f.get("url") and f.get("vcodec") != "none"]
        formats.sort(key=lambda f: (f.get("height") or 0, f.get("filesize") or 0), reverse=True)
        direct_url = formats[0].get("url") if formats else None
    if not direct_url:
        return None
    title = info.get("title") or "video"
    ext = info.get("ext") or "mp4"
    return {"name": f"{title}.{ext}", "url": direct_url}


def get_youtube_info(url):
    return get_video_info(url)


def filter_formats(formats):
    return [f for f in formats if f.get("url") and f.get("vcodec") != "none"]

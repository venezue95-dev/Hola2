from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse


class UrlPolicyError(ValueError):
    pass


def _host_ips(host: str):
    try:
        return {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        raise UrlPolicyError(f"No se pudo resolver el host: {host}") from exc


def _is_private_or_reserved(ip):
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified
    )


def validate_public_url(url: str, allowed_hosts=None) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UrlPolicyError("Solo se permiten URLs HTTP o HTTPS.")
    if parsed.username or parsed.password:
        raise UrlPolicyError("No se permiten credenciales incrustadas en la URL.")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host in {"localhost", "localhost.localdomain"}:
        raise UrlPolicyError("El host no es válido para una descarga pública.")

    patterns = allowed_hosts
    if patterns is None:
        raw = os.getenv("DOWNLOAD_ALLOWED_HOSTS", "").strip()
        patterns = [x.strip().lower() for x in raw.split(",") if x.strip()] if raw else None
    if patterns:
        if not any(host == item or host.endswith("." + item.lstrip("*.")) for item in patterns):
            raise UrlPolicyError(f"Host no permitido por la política: {host}")

    if any(_is_private_or_reserved(ip) for ip in _host_ips(host)):
        raise UrlPolicyError("La URL apunta a una dirección privada o reservada.")
    return parsed.geturl()

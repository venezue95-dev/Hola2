"""Código REVISTA1 para representar y reconstruir un archivo partido.

No levanta ningún servidor. El código contiene un manifiesto comprimido con las
URLs de las partes; un descargador compatible las obtiene y concatena en orden.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import zlib
from typing import Callable, Optional

import requests

PREFIX = "https://5.4.3.2.1:"
LEGACY_PREFIXES = ("REVISTA1:", "ETCHUNK1:")


def _enc(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _dec(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def build_code(filename: str, original_size: int, parts: list[dict],
               sha256: Optional[str] = None) -> str:
    payload = {
        "version": 1,
        "filename": os.path.basename(filename),
        "size": int(original_size),
        "sha256": sha256,
        "created": int(time.time()),
        "parts": [
            {"index": int(p["index"]), "url": p["url"]}
            for p in sorted(parts, key=lambda x: int(x["index"]))
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return PREFIX + _enc(zlib.compress(raw, 9))


def parse_code(code: str) -> dict:
    code = code.strip()
    prefix = PREFIX if code.startswith(PREFIX) else next(
        (item for item in LEGACY_PREFIXES if code.startswith(item)), None
    )
    if not prefix:
        raise ValueError("código de servidor inválido")
    payload = json.loads(zlib.decompress(_dec(code[len(prefix):])).decode())
    if payload.get("version") != 1 or not payload.get("parts"):
        raise ValueError("manifiesto vacío o versión no soportada")
    payload["parts"] = sorted(payload["parts"], key=lambda p: int(p["index"]))
    return payload


def download_code(code: str, output_path: str,
                  progress: Optional[Callable[[int, int, int], None]] = None,
                  timeout=(20, 300)) -> dict:
    manifest = parse_code(code)
    total = len(manifest["parts"])
    written = 0
    digest = hashlib.sha256()
    with open(output_path, "wb") as output:
        for current, part in enumerate(manifest["parts"], 1):
            with requests.get(part["url"], stream=True, timeout=timeout) as response:
                response.raise_for_status()
                for block in response.iter_content(chunk_size=1024 * 1024):
                    if block:
                        output.write(block)
                        digest.update(block)
                        written += len(block)
            if progress:
                progress(current, total, written)
    expected = manifest.get("sha256")
    if expected and digest.hexdigest() != expected:
        raise ValueError("hash SHA-256 no coincide")
    if manifest.get("size") is not None and written != int(manifest["size"]):
        raise ValueError(f"tamaño incorrecto: {written} != {manifest['size']}")
    return {"filename": manifest["filename"], "size": written, "output": output_path}

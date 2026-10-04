"""Subida de archivos grandes en partes a un Moodle autorizado.

Cada parte se carga como un archivo independiente mediante MoodleClient.upload_file
(o upload_file_draft). El módulo no pone credenciales en URLs ni inventa un
protocolo de reensamblado: el consumidor debe conocer el manifiesto devuelto.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

class ChunkedUploadError(RuntimeError):
    """Error de una parte o de la validación del lote."""


class ChunkedMoodleUploader:
    def __init__(self, client, chunk_size_mb: int = 20,
                 max_retries: int = 3, retry_delay: float = 2.0):
        if chunk_size_mb < 1:
            raise ValueError("chunk_size_mb debe ser >= 1")
        self.client = client
        self.chunk_size = chunk_size_mb * 1024 * 1024
        self.max_retries = max(1, max_retries)
        self.retry_delay = max(0.0, retry_delay)

    @staticmethod
    def _sha256(path: str, block_size: int = 1024 * 1024) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as source:
            while block := source.read(block_size):
                digest.update(block)
        return digest.hexdigest()

    def _split(self, source_path: str, work_dir: str) -> List[Dict]:
        os.makedirs(work_dir, exist_ok=True)
        source = Path(source_path)
        chunks: List[Dict] = []
        with source.open("rb") as src:
            index = 1
            while data := src.read(self.chunk_size):
                part_name = f"{source.name}.part{index:05d}"
                part_path = Path(work_dir) / part_name
                part_path.write_bytes(data)
                chunks.append({
                    "index": index,
                    "name": part_name,
                    "path": str(part_path),
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                })
                index += 1
        return chunks

    def upload(self, source_path: str, work_dir: str, *, mode: str = "evidence",
               evidence=None, itemid=None, progress: Optional[Callable] = None,
               progress_args=(), tokenize: bool = False,
               cancel_check: Optional[Callable[[], bool]] = None) -> Dict:
        if not os.path.isfile(source_path):
            raise FileNotFoundError(source_path)
        # Importación diferida: permite probar el particionado sin instalar
        # todo el stack HTTP del bot.
        from MoodleClient import StopUploadException

        original_name = os.path.basename(source_path)
        original_size = os.path.getsize(source_path)
        original_sha256 = self._sha256(source_path)
        parts = self._split(source_path, work_dir)
        uploaded: List[Dict] = []

        try:
            for part in parts:
                if cancel_check and cancel_check():
                    raise StopUploadException("Subida cancelada")

                response = None
                last_error = None
                for attempt in range(1, self.max_retries + 1):
                    try:
                        if mode == "evidence":
                            _, response = self.client.upload_file(
                                part["path"], evidence, itemid,
                                progressfunc=progress, args=progress_args,
                                tokenize=tokenize)
                        elif mode == "draft":
                            _, response = self.client.upload_file_draft(
                                part["path"], None, itemid,
                                progressfunc=progress, args=progress_args,
                                tokenize=tokenize)
                        elif mode == "calendar":
                            _, response = self.client.upload_file_calendar(
                                part["path"], progressfunc=progress,
                                args=progress_args, tokenize=tokenize)
                        else:
                            raise ValueError(f"modo Moodle no soportado: {mode}")
                        if response:
                            break
                    except StopUploadException:
                        raise
                    except Exception as exc:
                        last_error = exc
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay * attempt)

                if not response:
                    raise ChunkedUploadError(
                        f"falló la parte {part['index']}/{len(parts)} "
                        f"({part['name']}): {last_error or 'respuesta vacía'}"
                    )
                uploaded.append({
                    "index": part["index"],
                    "name": part["name"],
                    "size": part["size"],
                    "sha256": part["sha256"],
                    "response": response,
                })

            return {
                "type": "chunked",
                "original_name": original_name,
                "original_size": original_size,
                "original_sha256": original_sha256,
                "chunk_size": self.chunk_size,
                "chunks": uploaded,
                "manifest": json.dumps({
                    "name": original_name,
                    "size": original_size,
                    "sha256": original_sha256,
                    "parts": [
                        {"index": p["index"], "name": p["name"],
                         "size": p["size"], "sha256": p["sha256"]}
                        for p in uploaded
                    ],
                }, ensure_ascii=False),
            }
        finally:
            for part in parts:
                try:
                    os.remove(part["path"])
                except FileNotFoundError:
                    pass

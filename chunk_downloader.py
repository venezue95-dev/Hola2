#!/usr/bin/env python3
"""Descarga y reconstruye un código con prefijo https://5.4.3.2.1.

Uso:
    python chunk_downloader.py 'https://5.4.3.2.1...' 
    python chunk_downloader.py 'https://5.4.3.2.1...' -o archivo_salida.bin
"""
from __future__ import annotations

import argparse
import os
import sys

from chunk_code import download_code, parse_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconstruye archivos desde un código de chunks")
    parser.add_argument("code", help="Código https://5.4.3.2.1 generado por el bot")
    parser.add_argument("-o", "--output", help="Ruta de salida; por defecto usa el nombre original")
    args = parser.parse_args()

    try:
        manifest = parse_code(args.code)
        output = args.output or manifest["filename"]
        print(f"Archivo: {manifest['filename']}")
        print(f"Partes: {len(manifest['parts'])}")
        print(f"Tamaño esperado: {manifest['size']} bytes")

        def progress(current: int, total: int, written: int) -> None:
            pct = current * 100 // total
            print(f"\rDescargando: {pct:3d}% ({current}/{total}) — {written} bytes", end="", flush=True)

        result = download_code(args.code, output, progress=progress)
        print(f"\nOK: {os.path.abspath(result['output'])}")
        print(f"Tamaño reconstruido: {result['size']} bytes")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

import os
import re
import unicodedata
from urllib.parse import unquote, urlparse


def slugify(value, allow_unicode=False):
    value = str(value or "archivo_descargado").strip()
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[\x00-\x1f\\/:*?\"<>|]", "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or "archivo_descargado"


def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, "Yi", suffix)


def req_file_size(req):
    try:
        return max(0, int(req.headers.get("content-length", 0)))
    except (TypeError, ValueError):
        return 0


def get_url_file_name(url, req=None):
    if req is not None:
        disposition = req.headers.get("Content-Disposition", "")
        match = re.search(r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)", disposition, re.I)
        if match:
            return slugify(unquote(match.group(1) or match.group(2)), allow_unicode=True)
    name = os.path.basename(unquote(urlparse(url).path))
    return slugify(name, allow_unicode=True) if name else "archivo_descargado"


def get_file_size(file):
    return os.stat(file).st_size


def createID(count=8):
    from random import randrange
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(alphabet[randrange(len(alphabet))] for _ in range(count))

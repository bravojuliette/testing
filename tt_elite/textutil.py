"""Normalizacion de texto/nombres y parseo de marcadores. Puro, sin I/O."""
from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def norm_text(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s.lower()).strip()
    return re.sub(r"\s+", " ", s)


def name_key(s) -> str:
    """Token-sorted key: 'Kolek, Maciej' y 'Maciej Kolek' colapsan al mismo jugador."""
    return " ".join(sorted(norm_text(s).split()))


def strong_name(a, b) -> bool:
    return name_key(a) == name_key(b)


def pair_key(a, b) -> str:
    x, y = sorted((name_key(a), name_key(b)))
    return x + "|" + y


def book_norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", norm_text(s))


def parse_score(s):
    """Marcador tipo '3-1' de tenis de mesa (al mejor de 5/7, gana quien llega a 3/4)."""
    m = re.search(r"\b([0-3])\s*[-:/]\s*([0-3])\b", str(s or ""))
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if max(a, b) != 3 or a == b:
        return None
    return a, b


def clean_html(x) -> str:
    return BeautifulSoup(str(x or ""), "html.parser").get_text(" ", strip=True)

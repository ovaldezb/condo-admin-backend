"""Normalización de texto para búsquedas sin distinguir mayúsculas ni acentos."""

from __future__ import annotations

import unicodedata


def normalize(text: str) -> str:
    """Minúsculas, sin acentos ni marcas combinantes, y con espacios colapsados.

    >>> normalize("  Condominios   del Bajío ")
    'condominios del bajio'
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_marks.split())

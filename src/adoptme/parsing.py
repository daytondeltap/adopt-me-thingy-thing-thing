"""Helpers for turning messy scraped text into clean values."""

from __future__ import annotations

import re

_NUMBER = re.compile(r"[-+]?\d*\.?\d+")
_VARIANT_TOKENS = {"neon", "mega", "fly", "ride", "fr", "f&r", "f/r"}


def parse_number(text: str | None) -> float | None:
    """'1,234.5' -> 1234.5, '12k' -> 12000.0, 'N/A' -> None."""
    if text is None:
        return None
    t = text.strip().lower().replace(",", "")
    m = _NUMBER.search(t)
    if not m:
        return None
    n = float(m.group())
    suffix = t[m.end():].strip()
    if suffix.startswith("k"):
        n *= 1_000
    elif suffix.startswith("m"):
        n *= 1_000_000
    return n


def norm_name(name: str) -> str:
    """Case/punctuation-insensitive key: "Shadow-Dragon!" -> "shadow dragon"."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def variant_key(*, neon: bool = False, mega: bool = False, fly: bool = False, ride: bool = False) -> str:
    base = "mega" if mega else "neon" if neon else "normal"
    flags = ("f" if fly else "") + ("r" if ride else "")
    return f"{base}_{flags}" if flags else base


def split_variant(raw_name: str) -> tuple[str, str]:
    """Pull variant words out of a display name.

    "Mega Neon Shadow Dragon FR" -> ("Shadow Dragon", "mega_fr")
    Only whole-word matches are removed, so pets like "Flyer" are untouched.
    """
    neon = mega = fly = ride = False
    kept: list[str] = []
    for word in raw_name.split():
        w = word.lower().strip("()[]")
        if w == "neon":
            neon = True
        elif w == "mega":
            mega = True
        elif w == "fly":
            fly = True
        elif w == "ride":
            ride = True
        elif w in {"fr", "f&r", "f/r"}:
            fly = ride = True
        else:
            kept.append(word)
    clean = " ".join(kept).strip() or raw_name.strip()
    return clean, variant_key(neon=neon, mega=mega, fly=fly, ride=ride)


def normalize_variant_input(text: str) -> str:
    """Accept user input like 'Neon', 'mega fr', 'any' and return a variant key."""
    t = text.strip().lower()
    if t in {"", "any", "all", "*"}:
        return "any"
    _, key = split_variant(t)
    return key

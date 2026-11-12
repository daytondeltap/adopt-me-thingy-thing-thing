"""Read explicit pet variant values embedded in Elvebredd's calculator."""

from __future__ import annotations

import json
import re
from math import isfinite
from pathlib import PurePosixPath

from bs4 import BeautifulSoup

from ..models import ValueRecord
from ..parsing import norm_name
from .base import Source

_SCRIPT_PREFIX = "self.__next_f.push("
_COLUMNS = {"rvalue": "normal", "nvalue": "neon", "mvalue": "mega"}
_POTIONS = {"nopotion": "", "fly": "_f", "ride": "_r", "fly&ride": "_fr"}


def flight_text(html: str) -> str:
    """Join the string chunks of the Next.js `__next_f` stream back into one text."""
    parts: list[str] = []
    for script in BeautifulSoup(html, "html.parser").find_all("script"):
        text = (script.string or "").strip()
        if not text.startswith(_SCRIPT_PREFIX) or not text.endswith(")"):
            continue
        try:
            chunk = json.loads(text[len(_SCRIPT_PREFIX):-1])
        except json.JSONDecodeError:
            continue
        if isinstance(chunk, list) and len(chunk) > 1 and chunk[0] == 1 and isinstance(chunk[1], str):
            parts.append(chunk[1])
    return "".join(parts)


def _enclosing_object(text: str, idx: int) -> dict | None:
    """The innermost JSON object that contains position `idx`, or None."""
    depth = 0
    for i in range(idx, -1, -1):
        ch = text[i]
        if ch == "}":
            depth += 1
        elif ch == "{":
            if depth == 0:
                try:
                    obj, _ = json.JSONDecoder().raw_decode(text[i:])
                except json.JSONDecodeError:
                    return None
                return obj if isinstance(obj, dict) else None
            depth -= 1
    return None


def _pet_name(obj: dict) -> str | None:
    name = obj.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    image = obj.get("image")
    if isinstance(image, str) and image.strip():
        return PurePosixPath(image).stem.strip() or None
    return None


class ElvebreddSource(Source):
    def fetch(self) -> list[ValueRecord]:
        respect = not self.config.get("ignore_robots", False)
        records: dict[tuple[str, str], ValueRecord] = {}
        for page in self.config["pages"]:
            html = self.client.get_text(page["url"], respect_robots=respect)
            for rec in self.parse(html):
                records[norm_name(rec.name), rec.variant] = rec
        return list(records.values())

    def parse(self, html: str) -> list[ValueRecord]:
        text = flight_text(html)
        if not text:
            raise ValueError("Elvebredd page has no __next_f payload (layout changed?)")
        records: dict[tuple[str, str], ValueRecord] = {}
        for match in re.finditer(r'"rvalue"\s*:', text):
            obj = _enclosing_object(text, match.start())
            if not obj:
                continue
            if obj.get("type", "pets") != "pets":
                continue
            name = _pet_name(obj)
            if not name:
                continue
            for column, variant in _COLUMNS.items():
                explicit = {
                    variant + suffix: obj[f"{column} - {label}"]
                    for label, suffix in _POTIONS.items()
                    if f"{column} - {label}" in obj
                }
                # Older payloads may lack potion columns. Keep their base value
                # under an explicit unspecified variant instead of guessing.
                if not explicit:
                    explicit = {variant + "_unspecified": obj.get(column)}
                for key, raw in explicit.items():
                    try:
                        value = float(raw)
                    except (TypeError, ValueError):
                        continue
                    if isfinite(value) and value > 0:
                        records[norm_name(name), key] = ValueRecord(self.name, name, "pets", key, value)
        if not records:
            raise ValueError("Elvebredd returned no usable pet values")
        return list(records.values())

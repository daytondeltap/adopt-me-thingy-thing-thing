from __future__ import annotations

import json
import logging
from typing import Any

from bs4 import BeautifulSoup

from ..models import ValueRecord
from ..parsing import parse_number, split_variant
from .base import Source

log = logging.getLogger(__name__)


def dig(obj: Any, path: str | None) -> Any:
    """dig({'a': {'b': [1]}}, 'a.b.0') -> 1. Empty path returns obj."""
    if not path:
        return obj
    for part in path.split("."):
        if isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
        if obj is None:
            return None
    return obj


class JsonSource(Source):
    """Extract values from JSON, either a real endpoint or JSON embedded in a page.

    Handy when a site renders from JSON (e.g. a Next.js __NEXT_DATA__ script tag
    or an XHR endpoint you spotted with `probe`).

    mapping:
      embedded_selector  optional CSS selector of a <script> tag holding the JSON
                         (omit when the URL itself returns JSON)
      items_path         dotted path to the list of pets
      name, value, demand  dotted paths inside each item
      variants           alternative to `value`: {"normal": path, "neon": path, ...}
    """

    @property
    def is_configured(self) -> bool:
        m = self.config.get("mapping") or {}
        return bool(self.config.get("pages")) and bool(m.get("name")) and bool(m.get("value") or m.get("variants"))

    def fetch(self) -> list[ValueRecord]:
        records: list[ValueRecord] = []
        for page in self.config["pages"]:
            text = self.client.get_text(page["url"])
            records.extend(self.parse(text, page.get("category", "")))
        return records

    def parse(self, text: str, category: str = "") -> list[ValueRecord]:
        m = self.config["mapping"]
        if m.get("embedded_selector"):
            tag = BeautifulSoup(text, "html.parser").select_one(m["embedded_selector"])
            if tag is None:
                log.warning("%s: embedded_selector %r not found", self.name, m["embedded_selector"])
                return []
            data = json.loads(tag.string or tag.get_text())
        else:
            data = json.loads(text)

        items = dig(data, m.get("items_path"))
        if not isinstance(items, list):
            log.warning("%s: items_path %r did not resolve to a list", self.name, m.get("items_path"))
            return []

        out: list[ValueRecord] = []
        for item in items:
            raw_name = dig(item, m["name"])
            if not isinstance(raw_name, str) or not raw_name.strip():
                continue
            clean_name, name_variant = split_variant(raw_name)
            demand = dig(item, m.get("demand")) if m.get("demand") else None
            demand = str(demand) if demand is not None else None
            if m.get("variants"):
                for variant, path in m["variants"].items():
                    value = parse_number(str(dig(item, path))) if dig(item, path) is not None else None
                    if value is not None:
                        out.append(ValueRecord(self.name, clean_name, category, variant, value, demand))
            else:
                raw_value = dig(item, m["value"])
                value = parse_number(str(raw_value)) if raw_value is not None else None
                if value is not None:
                    out.append(ValueRecord(self.name, clean_name, category, name_variant, value, demand))
        return out

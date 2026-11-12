"""Read the pet value payload embedded in the public Adopt Me Values page."""

import json
from math import isfinite

from bs4 import BeautifulSoup

from ..models import ValueRecord
from ..parsing import variant_key
from .base import Source

_SCRIPT_PREFIX = "self.__next_f.push("
_ITEMS_KEY = '"initialItems":'
_VARIANTS = {"reg": {}, "neon": {"neon": True}, "mega": {"mega": True}}
_POTIONS = {
    "np": {}, "f": {"fly": True}, "r": {"ride": True},
    "rf": {"fly": True, "ride": True},
}


class AdoptMeValuesSource(Source):
    def fetch(self) -> list[ValueRecord]:
        records = {}
        for page in self.config["pages"]:
            for row in self.parse(self.client.get_text(page["url"])):
                records[row.name, row.variant] = row
        return list(records.values())

    def parse(self, html: str) -> list[ValueRecord]:
        payload = []
        for script in BeautifulSoup(html, "html.parser").find_all("script"):
            text = (script.string or "").strip()
            if not text.startswith(_SCRIPT_PREFIX) or not text.endswith(")"):
                continue
            chunk = json.loads(text[len(_SCRIPT_PREFIX):-1])
            if isinstance(chunk, list) and len(chunk) > 1 and chunk[0] == 1 and isinstance(chunk[1], str):
                payload.append(chunk[1])
        _, key, remainder = "".join(payload).partition(_ITEMS_KEY)
        if not key:
            raise ValueError("Adopt Me Values list payload was not found")
        items, _ = json.JSONDecoder().raw_decode(remainder.lstrip())
        if not isinstance(items, list):
            raise ValueError("Adopt Me Values list payload has an unexpected format")
        records = []
        for item in items:
            if not isinstance(item, dict) or item.get("category") != "Pets":
                continue
            name, metadata = item.get("name"), item.get("metadata")
            if not isinstance(name, str) or not name.strip() or not isinstance(metadata, dict):
                continue
            for prefix, variant_flags in _VARIANTS.items():
                values = metadata.get(prefix + "Value")
                demand = metadata.get(prefix + "Demand")
                if not isinstance(values, dict):
                    continue
                for potion, potion_flags in _POTIONS.items():
                    try:
                        value = float(values.get(potion))
                    except (TypeError, ValueError):
                        continue
                    if not isfinite(value) or value <= 0:
                        continue
                    variant = variant_key(**variant_flags, **potion_flags)
                    rating = demand.get(potion) if isinstance(demand, dict) else demand
                    label = str(rating) if rating is not None else None
                    records.append(ValueRecord(self.name, name.strip(), "pets", variant, value, label))
        if not records:
            raise ValueError("Adopt Me Values returned no usable pet values")
        return records

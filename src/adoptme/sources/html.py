from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from ..models import ValueRecord
from ..parsing import parse_number, split_variant
from .base import Source

log = logging.getLogger(__name__)


class HtmlSource(Source):
    """Extract values from server-rendered HTML using CSS selectors from config.

    selectors:
      row       CSS selector matching one element per pet
      name      CSS selector (inside the row) for the pet name
      value     CSS selector for a single value; variant words in the name
                ("Neon Frost Dragon") decide the variant
      variants  alternative to `value`: {"normal": css, "neon": css, "mega": css}
                for sites that show every variant in one row
      demand    optional CSS selector for a demand label
    """

    @property
    def is_configured(self) -> bool:
        sel = self.config.get("selectors") or {}
        has_value = bool(sel.get("value")) or bool(sel.get("variants"))
        return bool(self.config.get("pages")) and bool(sel.get("row")) and bool(sel.get("name")) and has_value

    def fetch(self) -> list[ValueRecord]:
        records: list[ValueRecord] = []
        for page in self.config["pages"]:
            html = self.client.get_text(page["url"])
            records.extend(self.parse(html, page.get("category", "")))
        return records

    def parse(self, html: str, category: str = "") -> list[ValueRecord]:
        sel = self.config["selectors"]
        soup = BeautifulSoup(html, "html.parser")
        out: list[ValueRecord] = []
        rows = soup.select(sel["row"])
        if not rows:
            log.warning("%s: row selector %r matched nothing (layout changed?)", self.name, sel["row"])
        for row in rows:
            name_el = row.select_one(sel["name"])
            if name_el is None:
                continue
            raw_name = name_el.get_text(" ", strip=True)
            if not raw_name:
                continue
            clean_name, name_variant = split_variant(raw_name)
            demand = None
            if sel.get("demand"):
                demand_el = row.select_one(sel["demand"])
                demand = demand_el.get_text(" ", strip=True) if demand_el else None

            if sel.get("variants"):
                for variant, css in sel["variants"].items():
                    el = row.select_one(css)
                    value = parse_number(el.get_text(" ", strip=True)) if el else None
                    if value is not None:
                        out.append(ValueRecord(self.name, clean_name, category, variant, value, demand))
            else:
                el = row.select_one(sel["value"])
                value = parse_number(el.get_text(" ", strip=True)) if el else None
                if value is not None:
                    out.append(ValueRecord(self.name, clean_name, category, name_variant, value, demand))
        return out

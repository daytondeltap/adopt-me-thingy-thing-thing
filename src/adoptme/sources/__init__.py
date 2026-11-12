"""Source registry: builds Source objects from config/sources.json."""

from __future__ import annotations

import json
import logging

from ..http import PoliteClient
from .adoptmevalues import AdoptMeValuesSource
from .base import Source
from .elvebredd import ElvebreddSource
from .html import HtmlSource
from .jsonapi import JsonSource

log = logging.getLogger(__name__)

SOURCE_TYPES: dict[str, type[Source]] = {
    "html": HtmlSource,
    "json": JsonSource,
    "adoptmevalues": AdoptMeValuesSource,
    "elvebredd": ElvebreddSource,
}


def load_sources(config_path: str, client: PoliteClient) -> list[Source]:
    with open(config_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    sources: list[Source] = []
    for name, cfg in raw.items():
        if name.startswith("_"):
            continue
        if not cfg.get("enabled", True):
            log.info("source %s is disabled", name)
            continue
        cls = SOURCE_TYPES.get(cfg.get("type", "html"))
        if cls is None:
            log.error("source %s has unknown type %r", name, cfg.get("type"))
            continue
        source = cls(name, cfg, client)
        if not source.is_configured:
            log.warning("source %s is not configured yet; run `probe` (skipping)", name)
            continue
        sources.append(source)
    return sources

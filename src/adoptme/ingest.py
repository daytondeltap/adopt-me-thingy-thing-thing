"""One ingest pass: fetch every source, store changes, work out which alerts to send."""

from __future__ import annotations

import logging
import sqlite3

from . import db
from .models import Alert, Change
from .sources.base import Source
from .watchlist import match_changes

log = logging.getLogger(__name__)


def run_once(conn: sqlite3.Connection, sources: list[Source]) -> tuple[list[Change], list[Alert]]:
    """A failure in one source never stops the others."""
    changes: list[Change] = []
    for source in sources:
        try:
            records = source.fetch()
        except Exception:
            log.exception("source %s failed", source.name)
            continue
        stored = 0
        for rec in records:
            change = db.record_snapshot(conn, rec)
            if change:
                changes.append(change)
                stored += 1
        conn.commit()
        log.info("source %s: %d records, %d changed", source.name, len(records), stored)
    alerts = match_changes(conn, changes)
    conn.commit()
    return changes, alerts

"""Decide which watches fire for a value change."""

from __future__ import annotations

import sqlite3

from . import db
from .models import Alert, Change, Watch


def _fires(watch: Watch, change: Change) -> bool:
    if watch.variant != "any" and watch.variant != change.variant:
        return False
    prev, cur, limit = change.prev_value, change.value, watch.threshold
    if watch.kind == "any_change":
        return prev is not None  # a first-ever sighting isn't a "change"
    if limit is None:
        return False
    if watch.kind == "drop_below":
        return cur <= limit and (prev is None or prev > limit)  # fire on the crossing only
    if watch.kind == "rise_above":
        return cur >= limit and (prev is None or prev < limit)
    return False


def match_changes(conn: sqlite3.Connection, changes: list[Change]) -> list[Alert]:
    """Return alerts to send, recording each so a watch never fires twice for one snapshot."""
    alerts: list[Alert] = []
    for change in changes:
        for watch in db.watches_for(conn, change.name_norm):
            if _fires(watch, change) and db.log_alert(conn, watch.id, change.snapshot_id):
                alerts.append(Alert(watch, change))
    return alerts

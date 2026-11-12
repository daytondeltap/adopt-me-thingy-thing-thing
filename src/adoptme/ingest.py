"""One ingest pass: fetch every source, store changes, work out which alerts to send."""

from __future__ import annotations

import logging
import sqlite3
from collections import Counter, defaultdict
from statistics import median

from . import db
from .models import Alert, Change
from .parsing import norm_name
from .sources.base import Source
from .watchlist import match_changes

log = logging.getLogger(__name__)


def _rebase_factor(changes: list[Change], variants_per_pet: Counter[str]) -> float | None:
    # Each pet gets one vote regardless of how many variants the source lists.
    ratios = defaultdict(list)
    for change in changes:
        if change.prev_value and change.prev_value > 0:
            ratios[change.name_norm].append(change.value / change.prev_value)
    votes = [median(values) for name, values in ratios.items()
             if len(values) > variants_per_pet[name] / 2]
    if len(votes) < 10:
        return None
    factor = median(votes)
    matching = sum(abs(ratio / factor - 1) <= 0.02 for ratio in votes) if factor > 0 else 0
    if abs(factor - 1) >= 0.10 and matching >= max(10, 0.80 * len(variants_per_pet)):
        return factor
    return None


def run_once(conn: sqlite3.Connection, sources: list[Source]) -> tuple[list[Change], list[Alert]]:
    """A failure in one source never stops the others."""
    changes: list[Change] = []
    alertable: list[Change] = []
    for source in sources:
        try:
            records = source.fetch()
        except Exception:
            log.exception("source %s failed", source.name)
            continue
        source_changes: list[Change] = []
        for rec in records:
            change = db.record_snapshot(conn, rec)
            if change:
                source_changes.append(change)
        changes.extend(source_changes)
        variants_per_pet = Counter(name for name, _ in {
            (norm_name(rec.name), rec.variant) for rec in records if rec.value is not None
        })
        factor = _rebase_factor(source_changes, variants_per_pet)
        if factor is None:
            alertable.extend(source_changes)
        else:
            log.warning("source %s: possible unit rebase (×%.4g), suppressing this poll's alerts",
                        source.name, factor)
        log.info("source %s: %d records, %d changed", source.name, len(records), len(source_changes))
    alerts = match_changes(conn, alertable)
    conn.commit()
    return changes, alerts

"""Export value history for the static dashboard without exporting watches or alerts."""

import json
from itertools import groupby
from pathlib import Path
import sqlite3

from .db import utcnow


def export_dashboard(conn: sqlite3.Connection, output: Path) -> int:
    rows = conn.execute(
        """SELECT i.display_name, s.source, s.variant, s.value, s.demand, s.captured_at
           FROM snapshots s JOIN items i ON i.id = s.item_id
           WHERE i.category = 'pets'
           ORDER BY i.name_norm, s.source, s.variant, s.captured_at, s.id"""
    )
    series = []
    for (pet, source, variant), group in groupby(rows, key=lambda row: tuple(row)[:3]):
        series.append({
            "pet": pet, "source": source, "variant": variant,
            "points": [[row["captured_at"], row["value"], row["demand"]] for row in group],
        })
    output.write_text(
        json.dumps({"version": 1, "exported_at": utcnow().isoformat(), "series": series},
                   ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return len(series)

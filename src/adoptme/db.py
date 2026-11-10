"""SQLite storage: items, value snapshots (history), watchlists, alert log."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

from .models import Change, ValueRecord, Watch
from .parsing import norm_name

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY,
    name_norm    TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    category     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY,
    item_id     INTEGER NOT NULL REFERENCES items(id),
    source      TEXT NOT NULL,
    variant     TEXT NOT NULL,
    value       REAL NOT NULL,
    demand      TEXT,
    captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_lookup
    ON snapshots(item_id, source, variant, captured_at);

CREATE TABLE IF NOT EXISTS watchlist (
    id           INTEGER PRIMARY KEY,
    user_id      TEXT NOT NULL,
    name_norm    TEXT NOT NULL,
    display_name TEXT NOT NULL,
    variant      TEXT NOT NULL DEFAULT 'any',
    kind         TEXT NOT NULL CHECK (kind IN ('any_change', 'drop_below', 'rise_above')),
    threshold    REAL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_watchlist_name ON watchlist(name_norm);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY,
    watch_id    INTEGER NOT NULL REFERENCES watchlist(id) ON DELETE CASCADE,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    sent_at     TEXT NOT NULL,
    UNIQUE (watch_id, snapshot_id)
);
"""

# Unchanged values are re-recorded at most this often, so history has regular points
# without storing a row on every poll.
HEARTBEAT = timedelta(hours=24)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def session(path: str) -> Iterator[sqlite3.Connection]:
    """Short-lived connection; safe to use from worker threads."""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- snapshots -----------------------------------------------------------------


def _item_id(conn: sqlite3.Connection, name: str, category: str) -> tuple[int, str]:
    key = norm_name(name)
    row = conn.execute("SELECT id FROM items WHERE name_norm = ?", (key,)).fetchone()
    if row:
        if category:
            conn.execute("UPDATE items SET category = ? WHERE id = ?", (category, row["id"]))
        return row["id"], key
    cur = conn.execute(
        "INSERT INTO items (name_norm, display_name, category) VALUES (?, ?, ?)",
        (key, name.strip(), category),
    )
    return cur.lastrowid, key


def record_snapshot(
    conn: sqlite3.Connection, rec: ValueRecord, now: datetime | None = None
) -> Change | None:
    """Store a value. Returns a Change only when the value differs from the last one.

    Unchanged values are skipped (except a daily heartbeat row, which returns None).
    """
    if rec.value is None:
        return None
    now = now or utcnow()
    item_id, key = _item_id(conn, rec.name, rec.category)
    last = conn.execute(
        """SELECT value, captured_at FROM snapshots
           WHERE item_id = ? AND source = ? AND variant = ?
           ORDER BY captured_at DESC, id DESC LIMIT 1""",
        (item_id, rec.source, rec.variant),
    ).fetchone()

    changed = last is None or abs(last["value"] - rec.value) > 1e-9
    stale = last is not None and now - datetime.fromisoformat(last["captured_at"]) >= HEARTBEAT
    if not changed and not stale:
        return None

    cur = conn.execute(
        """INSERT INTO snapshots (item_id, source, variant, value, demand, captured_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (item_id, rec.source, rec.variant, rec.value, rec.demand, _iso(now)),
    )
    if not changed:
        return None
    return Change(
        snapshot_id=cur.lastrowid,
        source=rec.source,
        name_norm=key,
        display_name=rec.name.strip(),
        variant=rec.variant,
        value=rec.value,
        prev_value=last["value"] if last else None,
    )


def latest_values(conn: sqlite3.Connection, name: str) -> list[sqlite3.Row]:
    """Most recent value per (source, variant) for a pet."""
    return conn.execute(
        """SELECT i.display_name, s.source, s.variant, s.value, s.demand, s.captured_at
           FROM snapshots s
           JOIN items i ON i.id = s.item_id
           WHERE i.name_norm = ?
             AND s.id = (SELECT s2.id FROM snapshots s2
                         WHERE s2.item_id = s.item_id AND s2.source = s.source
                           AND s2.variant = s.variant
                         ORDER BY s2.captured_at DESC, s2.id DESC LIMIT 1)
           ORDER BY s.variant, s.source""",
        (norm_name(name),),
    ).fetchall()


def history(
    conn: sqlite3.Connection,
    name: str,
    variant: str,
    source: str | None = None,
    days: int | None = None,
) -> list[tuple[datetime, float]]:
    sql = """SELECT s.captured_at, s.value FROM snapshots s
             JOIN items i ON i.id = s.item_id
             WHERE i.name_norm = ? AND s.variant = ?"""
    params: list = [norm_name(name), variant]
    if source:
        sql += " AND s.source = ?"
        params.append(source)
    if days:
        sql += " AND s.captured_at >= ?"
        params.append(_iso(utcnow() - timedelta(days=days)))
    sql += " ORDER BY s.captured_at, s.id"
    return [
        (datetime.fromisoformat(r["captured_at"]), r["value"])
        for r in conn.execute(sql, params).fetchall()
    ]


def search_item_names(conn: sqlite3.Connection, prefix: str, limit: int = 25) -> list[str]:
    return [
        r["display_name"]
        for r in conn.execute(
            "SELECT display_name FROM items WHERE name_norm LIKE ? ORDER BY display_name LIMIT ?",
            (f"%{norm_name(prefix)}%", limit),
        )
    ]


# --- watchlist -----------------------------------------------------------------


def _watch(row: sqlite3.Row) -> Watch:
    return Watch(
        id=row["id"],
        user_id=row["user_id"],
        name_norm=row["name_norm"],
        display_name=row["display_name"],
        variant=row["variant"],
        kind=row["kind"],
        threshold=row["threshold"],
    )


def add_watch(
    conn: sqlite3.Connection,
    user_id: str,
    name: str,
    variant: str,
    kind: str,
    threshold: float | None,
) -> Watch:
    if kind in {"drop_below", "rise_above"} and threshold is None:
        raise ValueError(f"'{kind}' needs a threshold")
    cur = conn.execute(
        """INSERT INTO watchlist (user_id, name_norm, display_name, variant, kind, threshold, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, norm_name(name), name.strip(), variant, kind, threshold, _iso(utcnow())),
    )
    return _watch(conn.execute("SELECT * FROM watchlist WHERE id = ?", (cur.lastrowid,)).fetchone())


def list_watches(conn: sqlite3.Connection, user_id: str) -> list[Watch]:
    rows = conn.execute("SELECT * FROM watchlist WHERE user_id = ? ORDER BY id", (user_id,))
    return [_watch(r) for r in rows]


def remove_watch(conn: sqlite3.Connection, user_id: str, watch_id: int) -> bool:
    cur = conn.execute("DELETE FROM watchlist WHERE id = ? AND user_id = ?", (watch_id, user_id))
    return cur.rowcount > 0


def watches_for(conn: sqlite3.Connection, name_norm: str) -> list[Watch]:
    return [_watch(r) for r in conn.execute("SELECT * FROM watchlist WHERE name_norm = ?", (name_norm,))]


def log_alert(conn: sqlite3.Connection, watch_id: int, snapshot_id: int) -> bool:
    """Returns False if this watch already alerted for this snapshot."""
    try:
        conn.execute(
            "INSERT INTO alerts (watch_id, snapshot_id, sent_at) VALUES (?, ?, ?)",
            (watch_id, snapshot_id, _iso(utcnow())),
        )
        return True
    except sqlite3.IntegrityError:
        return False

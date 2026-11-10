from datetime import datetime, timedelta, timezone

import pytest

from adoptme import db
from adoptme.ingest import run_once
from adoptme.messages import format_alert, format_forecast, variant_label
from adoptme.models import ValueRecord
from adoptme.predict import forecast
from adoptme.sources.base import Source

T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def rec(value, name="Shadow Dragon", variant="normal", source="elvebredd"):
    return ValueRecord(source, name, "pets", variant, value)


class FakeSource(Source):
    def __init__(self, name, records=None, boom=False):
        super().__init__(name, {}, None)
        self._records, self._boom = records or [], boom

    @property
    def is_configured(self):
        return True

    def fetch(self):
        if self._boom:
            raise RuntimeError("site down")
        return list(self._records)


# --- snapshots ---

def test_snapshot_only_stored_on_change_or_heartbeat(conn):
    assert db.record_snapshot(conn, rec(100), T0).prev_value is None  # first sighting
    assert db.record_snapshot(conn, rec(100), T0 + timedelta(hours=1)) is None  # unchanged
    assert db.record_snapshot(conn, rec(100), T0 + timedelta(hours=25)) is None  # heartbeat row, no change
    change = db.record_snapshot(conn, rec(120), T0 + timedelta(hours=26))
    assert change.prev_value == 100 and change.value == 120
    n = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    assert n == 3  # first, heartbeat, change


def test_none_value_ignored(conn):
    assert db.record_snapshot(conn, rec(None), T0) is None
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0


def test_same_pet_different_sources_tracked_separately(conn):
    db.record_snapshot(conn, rec(100, source="a"), T0)
    change = db.record_snapshot(conn, rec(110, source="b"), T0)
    assert change.prev_value is None  # b has no earlier value, even though a does


def test_name_matching_is_case_and_punctuation_insensitive(conn):
    db.record_snapshot(conn, rec(100, name="Shadow Dragon"), T0)
    assert db.record_snapshot(conn, rec(100, name="shadow-dragon"), T0 + timedelta(hours=1)) is None
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1


def test_latest_values_and_history(conn):
    for i, v in enumerate([100, 110, 120]):
        db.record_snapshot(conn, rec(v), T0 + timedelta(days=i))
    rows = db.latest_values(conn, "shadow dragon")
    assert len(rows) == 1 and rows[0]["value"] == 120
    hist = db.history(conn, "Shadow Dragon", "normal")
    assert [v for _, v in hist] == [100, 110, 120]


# --- watchlist / ingest ---

def test_drop_below_fires_only_on_crossing(conn):
    db.add_watch(conn, "u1", "Shadow Dragon", "any", "drop_below", 100)
    s = FakeSource("elvebredd", [rec(120)])
    run_once(conn, [s])
    s._records = [rec(95)]
    _, alerts = run_once(conn, [s])
    assert len(alerts) == 1
    assert "dropped to or below your 100" in format_alert(alerts[0])
    s._records = [rec(90)]
    _, alerts = run_once(conn, [s])
    assert alerts == []  # already below; no repeat


def test_rise_above_and_any_change(conn):
    db.add_watch(conn, "u1", "Shadow Dragon", "neon", "rise_above", 500)
    db.add_watch(conn, "u2", "Shadow Dragon", "any", "any_change", None)
    s = FakeSource("adoptmevalues", [rec(400, variant="neon"), rec(50)])
    _, alerts = run_once(conn, [s])
    assert alerts == []  # first sightings: no any_change, below target
    s._records = [rec(550, variant="neon"), rec(55)]
    _, alerts = run_once(conn, [s])
    kinds = sorted((a.watch.user_id, a.watch.kind) for a in alerts)
    assert kinds == [("u1", "rise_above"), ("u2", "any_change"), ("u2", "any_change")]


def test_variant_filter(conn):
    db.add_watch(conn, "u1", "Shadow Dragon", "mega", "any_change", None)
    s = FakeSource("e", [rec(100, variant="neon")])
    run_once(conn, [s])
    s._records = [rec(200, variant="neon")]
    assert run_once(conn, [s])[1] == []


def test_failing_source_does_not_block_others(conn):
    good = FakeSource("good", [rec(10)])
    bad = FakeSource("bad", boom=True)
    changes, _ = run_once(conn, [bad, good])
    assert len(changes) == 1


def test_watch_validation_and_ownership(conn):
    with pytest.raises(ValueError):
        db.add_watch(conn, "u1", "Owl", "any", "drop_below", None)
    w = db.add_watch(conn, "u1", "Owl", "any", "any_change", None)
    assert not db.remove_watch(conn, "someone-else", w.id)
    assert db.remove_watch(conn, "u1", w.id)
    assert db.list_watches(conn, "u1") == []


def test_alert_deduped_per_snapshot(conn):
    w = db.add_watch(conn, "u1", "Owl", "any", "any_change", None)
    snap = db.record_snapshot(conn, rec(10, name="Owl"), T0)
    assert db.log_alert(conn, w.id, snap.snapshot_id)
    assert not db.log_alert(conn, w.id, snap.snapshot_id)


# --- prediction & messages ---

def series(values):
    return [(T0 + timedelta(days=i), v) for i, v in enumerate(values)]


def test_forecast_rising_falling_stable():
    assert forecast(series([100, 105, 110, 115, 120, 125, 130])).direction == "rising"
    assert forecast(series([130, 125, 120, 115, 110, 105, 100])).direction == "falling"
    assert forecast(series([100, 100, 101, 100, 100, 101, 100])).direction == "stable"


def test_forecast_needs_data():
    f = forecast(series([100, 110]))
    assert f.direction == "insufficient_data" and f.points == 2
    assert "Not enough history" in format_forecast("Owl", "normal", f, 7)


def test_variant_label():
    assert variant_label("normal") == "normal"
    assert variant_label("mega_fr") == "mega fly ride"
    assert variant_label("neon_f") == "neon fly"

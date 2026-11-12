import json
from datetime import datetime, timezone

from adoptme import db
from adoptme.dashboard import export_dashboard
from adoptme.models import ValueRecord
from adoptme.sources.adoptmevalues import AdoptMeValuesSource


def test_adoptmevalues_embedded_list():
    items = [
        {"name": "Test Pet", "category": "Pets", "metadata": {
            "regValue": {"np": "1.25", "rf": "1.0"},
            "regDemand": {"rf": "8"},
            "megaValue": {"f": "5.25", "r": "N/A", "np": "0"},
        }},
        {"name": "Test Toy", "category": "Toys", "metadata": {"regValue": {"np": 3}}},
    ]
    payload = '1:{"initialItems":' + json.dumps(items) + '}\n'
    split = payload.index("Test Pet")
    html = "".join(
        f"<script>self.__next_f.push({json.dumps([1, part])})</script>"
        for part in (payload[:split], payload[split:])
    )
    records = AdoptMeValuesSource("adoptmevalues", {}, None).parse(html)
    assert [(r.name, r.variant, r.value, r.demand) for r in records] == [
        ("Test Pet", "normal", 1.25, None),
        ("Test Pet", "normal_fr", 1.0, "8"),
        ("Test Pet", "mega_f", 5.25, None),
    ]


def test_dashboard_export_keeps_history_separate_and_omits_watches(tmp_path):
    output = tmp_path / "export.json"
    with db.session(":memory:") as conn:
        db.add_watch(conn, "private-discord-user", "Test Pet", "any", "any_change", None)
        for day, value in [(1, 2), (2, 3)]:
            db.record_snapshot(
                conn, ValueRecord("adoptmevalues", "Test Pet", "pets", "normal", value, None),
                datetime(2026, 1, day, tzinfo=timezone.utc),
            )
        db.record_snapshot(conn, ValueRecord("other", "Test Pet", "pets", "normal", 4, None))
        assert export_dashboard(conn, output) == 2
    raw = output.read_text()
    assert "private-discord-user" not in raw
    data = json.loads(raw)
    assert data["version"] == 1
    assert [[point[1] for point in row["points"]] for row in data["series"]] == [[2, 3], [4]]

import json

import httpx
import pytest

from adoptme.http import PoliteClient, RobotsDisallowed
from adoptme.sources.elvebredd import ElvebreddSource, flight_text


def page(*chunks: str) -> str:
    """Build a Next.js-style page: each chunk becomes self.__next_f.push([1, "..."])."""
    scripts = "".join(f"<script>self.__next_f.push({json.dumps([1, c])})</script>" for c in chunks)
    return f"<html><body>{scripts}</body></html>"


# Uses the one real fragment seen: "image":"/images/pets/Bat Dragon.png","rvalue":1001,"nvalue":2310,"mvalue":6550
RECORDS = (
    '[{"id":1,"image":"/images/pets/Bat Dragon.png","rvalue":1001,"nvalue":2310,"mvalue":6550},'
    '{"id":2,"name":"Shadow Dragon","meta":{"a":1},"rvalue":1200,"nvalue":"2,500x","mvalue":null}]'
)


def source(config=None, client=None) -> ElvebreddSource:
    return ElvebreddSource("elvebredd", config or {"pages": [{"url": "https://e.test/c"}]}, client)


def test_parses_real_fragment_name_from_image():
    recs = source().parse(page('0:{"pets":' + RECORDS + "}"))
    by = {(r.name, r.variant): r.value for r in recs}
    assert by[("Bat Dragon", "normal")] == 1001
    assert by[("Bat Dragon", "neon")] == 2310
    assert by[("Bat Dragon", "mega")] == 6550


def test_name_key_preferred_and_bad_values_skipped():
    by = {(r.name, r.variant): r.value for r in source().parse(page(RECORDS))}
    assert by[("Shadow Dragon", "normal")] == 1200
    assert ("Shadow Dragon", "neon") not in by  # "2,500x" isn't numeric
    assert ("Shadow Dragon", "mega") not in by  # null


def test_record_split_across_chunks():
    full = '{"image":"/images/pets/Owl.png","rvalue":50,"nvalue":120,"mvalue":300}'
    recs = source().parse(page(full[:30], full[30:]))
    assert {(r.name, r.variant): r.value for r in recs}[("Owl", "mega")] == 300


def test_duplicate_records_deduped():
    recs = source().parse(page(RECORDS, RECORDS))
    assert len(recs) == len({(r.name, r.variant) for r in recs})


def test_fails_loudly_when_layout_changes():
    with pytest.raises(ValueError, match="no __next_f"):
        source().parse("<html><body>nothing</body></html>")
    with pytest.raises(ValueError, match="no usable"):
        source().parse(page('{"unrelated":1}'))


def test_flight_text_ignores_non_flight_scripts():
    html = '<script>var x=1</script><script>self.__next_f.push([0])</script>' + page("abc")
    assert flight_text(html) == "abc"


# --- robots override ---

def make_client(respect=True):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /adopt-me-calculator")
        return httpx.Response(200, text=page(RECORDS))

    return PoliteClient("t", min_delay=0, respect_robots=respect,
                        transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_robots_blocks_by_default():
    src = source({"pages": [{"url": "https://e.test/adopt-me-calculator"}]}, make_client())
    with pytest.raises(RobotsDisallowed):
        src.fetch()


def test_ignore_robots_is_per_source_and_opt_in():
    client = make_client()
    src = source({"ignore_robots": True, "pages": [{"url": "https://e.test/adopt-me-calculator"}]}, client)
    assert len(src.fetch()) >= 3
    # The client default is untouched: another request still respects robots.
    with pytest.raises(RobotsDisallowed):
        client.get_text("https://e.test/adopt-me-calculator")


def test_shipped_config_loads_and_is_flagged():
    from pathlib import Path
    cfg = json.loads((Path(__file__).parent.parent / "config" / "sources.json").read_text())["elvebredd"]
    assert cfg["type"] == "elvebredd" and cfg["ignore_robots"] is True and cfg["_permission"]
    assert ElvebreddSource("elvebredd", cfg, None).is_configured

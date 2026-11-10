import json

import httpx

from adoptme.http import PoliteClient, RobotsDisallowed
from adoptme.sources.html import HtmlSource
from adoptme.sources.jsonapi import JsonSource, dig

TABLE_HTML = """
<table><tbody>
  <tr class="pet"><td class="n">Shadow Dragon</td><td class="d">High</td>
      <td class="normal">1,200</td><td class="neon">4.8k</td><td class="mega">N/A</td></tr>
  <tr class="pet"><td class="n">Bat Dragon</td><td class="d">Mid</td>
      <td class="normal">900</td><td class="neon">3,000</td><td class="mega">9,500</td></tr>
  <tr class="pet"><td class="n"></td></tr>
</tbody></table>
"""

CARD_HTML = """
<div class="card"><span class="title">Neon Frost Dragon</span><b class="v">350.5</b></div>
<div class="card"><span class="title">Mega Neon Owl FR</span><b class="v">80</b></div>
"""


def make_client(handler, **kw):
    return PoliteClient(
        "test-agent", min_delay=0, respect_robots=kw.pop("respect_robots", False),
        transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw,
    )


def test_html_source_variant_columns():
    cfg = {"pages": [{"url": "https://x.test/v"}], "selectors": {
        "row": "tr.pet", "name": ".n", "demand": ".d",
        "variants": {"normal": ".normal", "neon": ".neon", "mega": ".mega"}}}
    src = HtmlSource("x", cfg, client=None)
    recs = src.parse(TABLE_HTML, "pets")
    by = {(r.name, r.variant): r.value for r in recs}
    assert by[("Shadow Dragon", "normal")] == 1200
    assert by[("Shadow Dragon", "neon")] == 4800
    assert ("Shadow Dragon", "mega") not in by  # N/A skipped
    assert by[("Bat Dragon", "mega")] == 9500
    assert all(r.category == "pets" for r in recs)
    assert {r.demand for r in recs if r.name == "Bat Dragon"} == {"Mid"}


def test_html_source_variant_in_name():
    cfg = {"pages": [{"url": "u"}], "selectors": {"row": ".card", "name": ".title", "value": ".v"}}
    recs = HtmlSource("x", cfg, client=None).parse(CARD_HTML)
    assert [(r.name, r.variant, r.value) for r in recs] == [
        ("Frost Dragon", "neon", 350.5),
        ("Owl", "mega_fr", 80.0),
    ]


def test_html_source_unconfigured_until_selectors_set():
    assert not HtmlSource("x", {"pages": [{"url": "u"}], "selectors": {"row": None}}, None).is_configured
    assert HtmlSource("x", {"pages": [{"url": "u"}], "selectors": {"row": "a", "name": "b", "value": "c"}}, None).is_configured


def test_json_source_embedded_next_data():
    payload = {"props": {"pageProps": {"pets": [
        {"name": "Shadow Dragon", "vals": {"n": "1200", "ne": 4800}, "demand": "High"},
        {"name": "Bat Dragon", "vals": {"n": 900}},
    ]}}}
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script></html>'
    cfg = {"pages": [{"url": "u"}], "mapping": {
        "embedded_selector": "script#__NEXT_DATA__", "items_path": "props.pageProps.pets",
        "name": "name", "demand": "demand", "variants": {"normal": "vals.n", "neon": "vals.ne"}}}
    src = JsonSource("x", cfg, client=None)
    assert src.is_configured
    by = {(r.name, r.variant): r.value for r in src.parse(html)}
    assert by == {("Shadow Dragon", "normal"): 1200.0, ("Shadow Dragon", "neon"): 4800.0, ("Bat Dragon", "normal"): 900.0}


def test_json_source_plain_endpoint():
    cfg = {"pages": [{"url": "u"}], "mapping": {"items_path": "data", "name": "n", "value": "v"}}
    recs = JsonSource("x", cfg, None).parse(json.dumps({"data": [{"n": "Neon Owl", "v": 10}, {"n": "", "v": 1}]}))
    assert [(r.name, r.variant, r.value) for r in recs] == [("Owl", "neon", 10.0)]


def test_dig():
    assert dig({"a": {"b": [10, 20]}}, "a.b.1") == 20
    assert dig({"a": 1}, "a.b") is None
    assert dig({"a": 1}, "") == {"a": 1}


def test_client_respects_robots():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(200, text="ok")

    c = make_client(handler, respect_robots=True)
    assert c.get_text("https://x.test/public") == "ok"
    try:
        c.get_text("https://x.test/private/page")
        assert False, "should have been blocked"
    except RobotsDisallowed:
        pass


def test_client_no_robots_file_means_allowed():
    c = make_client(lambda r: httpx.Response(404) if r.url.path == "/robots.txt" else httpx.Response(200, text="hi"),
                    respect_robots=True)
    assert c.get_text("https://x.test/a") == "hi"


def test_client_backs_off_on_429_then_succeeds():
    calls = {"n": 0}
    sleeps: list[float] = []

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "7"}) if calls["n"] == 1 else httpx.Response(200, text="done")

    c = PoliteClient("a", min_delay=0, respect_robots=False,
                     transport=httpx.MockTransport(handler), sleep=sleeps.append)
    assert c.get_text("https://x.test/") == "done"
    assert 7.0 in sleeps


def test_client_enforces_min_delay_per_host():
    t = {"now": 100.0}
    sleeps: list[float] = []
    c = PoliteClient("a", min_delay=5, respect_robots=False,
                     transport=httpx.MockTransport(lambda r: httpx.Response(200, text="x")),
                     sleep=sleeps.append, clock=lambda: t["now"])
    c.get_text("https://x.test/1")
    t["now"] += 1  # only 1s later
    c.get_text("https://x.test/2")
    assert sleeps and abs(sleeps[0] - 4.0) < 1e-6

"""`probe`: inspect a page so you can fill in selectors in config/sources.json.

Run this on your own machine (the sites weren't reachable from the dev sandbox).
It prints what a scraper needs to know: embedded JSON, repeated elements that
look like list rows, and API-ish URLs referenced by the page.
"""

from __future__ import annotations

import re
from collections import Counter

from bs4 import BeautifulSoup

from .http import PoliteClient


def summarize(html: str, top: int = 12) -> str:
    soup = BeautifulSoup(html, "html.parser")
    lines: list[str] = []
    title = soup.title.get_text(strip=True) if soup.title else "(no title)"
    lines.append(f"title: {title}")
    lines.append(f"size: {len(html):,} chars")

    next_data = soup.select_one("script#__NEXT_DATA__")
    if next_data:
        lines.append("embedded JSON: found script#__NEXT_DATA__ -> use type 'json' with "
                     "embedded_selector 'script#__NEXT_DATA__'")
    ld = soup.select('script[type="application/ld+json"]')
    if ld:
        lines.append(f"embedded JSON: {len(ld)} JSON-LD block(s)")
    other_json = [
        s for s in soup.find_all("script")
        if s.get("type") == "application/json" and s.get("id") != "__NEXT_DATA__"
    ]
    for s in other_json[:5]:
        lines.append(f"embedded JSON: script#{s.get('id') or '?'} ({len(s.get_text())} chars)")

    api_hits = sorted(set(re.findall(r"""["'](/api/[^"'\s]+|https?://[^"'\s]*/api/[^"'\s]+)["']""", html)))
    if api_hits:
        lines.append("API-looking URLs referenced in the page:")
        lines.extend(f"  {u}" for u in api_hits[:15])

    # Repeated tag.class combinations are usually list rows / cards.
    combos: Counter[str] = Counter()
    for el in soup.find_all(True):
        classes = el.get("class") or []
        if classes:
            combos[f"{el.name}." + ".".join(classes)] += 1
    repeated = [(c, n) for c, n in combos.most_common(60) if n >= 5][:top]
    if repeated:
        lines.append("repeated elements (candidates for `row`):")
        lines.extend(f"  {n:5d}x  {c}" for c, n in repeated)
    else:
        lines.append("no repeated classed elements found; the page may be rendered by JavaScript.")

    tables = soup.find_all("table")
    if tables:
        lines.append(f"{len(tables)} <table> element(s); row selector could be 'table tbody tr'")

    if not (next_data or ld or other_json or repeated or tables):
        lines.append("hint: the HTML contains no data; the site likely loads values via an XHR "
                     "endpoint. Check your browser's Network tab for a JSON request.")
    return "\n".join(lines)


def probe(client: PoliteClient, url: str) -> str:
    return summarize(client.get_text(url))

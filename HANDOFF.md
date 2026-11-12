# Handoff: context for any AI assistant or developer

Paste this file (plus `README.md`) into a new chat to continue the project. Last updated 2026-11-12.

## 1. What the owner wants

A **personal-use** tool for the Roblox game Adopt Me that:

1. Scrapes **pet values** from value-list sites.
2. Sends **Discord alerts** when a pet the owner is watching changes value or crosses a target.
3. Eventually **predicts** whether a pet's value will rise or fall (the owner asked for a neural net).

The owner originally also wanted to "snipe" trades (auto-trade). That was ruled out; see section 2.

## 2. Decisions and constraints (do not undo without asking the owner)

- **Values only.** No scraping of trade ads. No automation of the Roblox/Adopt Me client. Automating the game risks account bans under Roblox's rules, so "sniping" means a fast alert only; the owner trades manually.
- **Sources:** Elvebredd and adoptmevalues.gg. The owner says they have the sites' permission to scrape values (neither has an API). This is the owner's statement; it has not been independently verified.
- **amvgg.com is excluded.** Its Terms of Service (section 8b) prohibit scraping, bots, and using its value data to build datasets or bots without written permission. Do not add it unless the owner gets written permission.
- **Politeness is mandatory:** robots.txt respected by default, minimum delay between requests per host, backoff on 429/5xx, descriptive User-Agent. Keep polling slow (30+ minutes); values change about daily.
- **Stack:** Python 3.11+, SQLite, `httpx` + BeautifulSoup, `discord.py`. Chosen for "just works", single process, no servers to run.
- **Prediction plan:** baseline trend line first, then gradient boosting, then a neural net only if the simpler models leave signal unused. A neural net is the wrong first tool for small, step-like, noisy data, and no model can foresee game updates (the biggest driver). Use walk-forward backtests, never random splits. Training needs weeks of recorded history, so getting scrapers live early starts that clock.

## 3. Current state

Repo: `daytondeltap/adopt-me-thingy-thing-thing` (branch `main`). Everything below is committed and pushed.

| Part | State |
|---|---|
| SQLite schema, value history (row on change plus a daily heartbeat), watchlists, alert dedupe | Done, tested |
| Polite HTTP client (robots, per-host delay, backoff) | Done, tested |
| Config-driven HTML extractor and JSON extractor | Done, tested on fixture data only |
| `probe` command to find selectors | Done |
| Alert matching (threshold alerts fire on *crossing*, not on every poll) | Done, tested |
| Discord bot: `/watch /unwatch /watchlist /value /trend` plus background poll loop | Built; confirmed it constructs and registers its 5 commands; **never run against real Discord** |
| Baseline trend predictor (`predict.py`, least-squares line) | Done, tested |
| 39 pytest tests | All passing |
| **Real selectors for Elvebredd and adoptmevalues.gg** | **NOT DONE (the blocker)** |
| Gradient boosting / neural net | Not started (needs history) |

## 4. The blocker: selectors are blank

`config/sources.json` has empty selectors, so both sources are skipped. The development sandbox could not reach either site with `curl` (proxy allowlist returned 403), so real HTML was never seen.

### What is known about adoptmevalues.gg (from a text-only page fetch, not raw HTML)

- Next.js site. `/values` is a list of stacked entries, not a `<table>`.
- Each pet is a link to `/values/pets/<slug>` (for example `/values/pets/bat-dragon`).
- Each entry shows: rarity, Fly/Ride icons, name, the letters "F R N M" (no numbers attached), **one value** (like `3.15`), a trend label (Stable/Dropping), demand (like `Demand8/10`), and "Updated 2 days ago".
- No embedded JSON, `__NEXT_DATA__` or API URLs were visible in the text.
- Unknown: whether per-variant (normal/neon/mega) values exist on each pet's detail page. If so, an extra step that visits each detail page would be needed.
- A likely row selector is `a[href^="/values/pets/"]`, but name/value selectors need the real HTML.

### What is known about Elvebredd

Nothing verified. The exact URL of its pet value list was not found (fetches were blocked; search returned only third-party articles).

### What the owner needs to supply (or what the next AI should obtain)

1. Outer HTML of one pet row from `https://adoptmevalues.gg/values` (browser Inspect, right-click the element, Copy outerHTML).
2. The part of one pet's detail page that shows its values.
3. Elvebredd's exact value-list URL and the same row HTML.

Alternative: run `python -m adoptme probe <url>` on the owner's machine and paste the output.

With that, fill in `config/sources.json`. The `html` type takes `selectors` (`row`, `name`, and either `value` or `variants`, optional `demand`); the `json` type takes a `mapping` block. Both are documented in `README.md`. The config is re-read every poll.

## 5. How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # set DISCORD_TOKEN and USER_AGENT
python -m adoptme init-db
python -m pytest              # expect 39 passed
python -m adoptme probe <url> # inspect a page for selectors
python -m adoptme ingest      # one pass, no Discord
python -m adoptme bot         # Discord bot plus poller
```

The Discord bot needs a token from the Discord developer portal and must share a server with the owner (alerts are DMs; an optional fallback channel ID is in `.env`).

## 6. Suggested next steps, in order

1. Get real HTML (section 4), fill in `config/sources.json`, and run `python -m adoptme ingest` until it stores sensible values. Add a fixture-based test using the real HTML.
2. Run the bot against a real Discord server and fix whatever breaks (untested so far).
3. Let it run to accumulate history. Decide on deployment (an always-on machine or cheap VPS; the database is a single SQLite file under `data/`).
4. Once there are a few weeks of data: build a backtest harness, then gradient boosting, then (only if justified) a neural net. Useful features: value history, demand, rarity, time since last game update, an update/event calendar.
5. Possible later additions: a small web dashboard, cross-source value comparison, charts of history.

## 7. Gotchas

- Variant keys are strings like `normal`, `neon`, `mega`, with `_f`, `_r` or `_fr` suffixes for fly/ride (for example `mega_fr`). Variant words in pet names are split out by `parsing.split_variant`.
- Items are matched across sources by a normalized name (lowercase, punctuation stripped).
- A first-ever sighting of a value does not fire `any_change` alerts.
- Never commit `.env` or `data/` (both are in `.gitignore`).
- Commits in this repo made through Claude carry `Co-Authored-By` and session lines; that is optional for future contributors.

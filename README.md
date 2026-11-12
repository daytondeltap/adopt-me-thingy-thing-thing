# Adopt Me value tracker

Personal-use tool that records pet values from value-list sites, DMs you on Discord when a pet you're watching changes or crosses a target, and gives a simple trend forecast.

**Sources:** Elvebredd and adoptmevalues.gg (permission obtained by the owner of this repo). amvgg.com is deliberately excluded: its terms prohibit scraping.

**Scope:** values only. It does not scrape trade ads and it does not automate anything in Roblox/Adopt Me. Alerts are notifications; you make the trades yourself.

> Continuing with an AI assistant or a new developer? Start with [HANDOFF.md](HANDOFF.md): it has the project context, decisions, current state and next steps.

## Status

| Part | State |
|---|---|
| SQLite storage, value history, watchlists, alert dedupe | done, tested |
| Polite HTTP client (robots.txt, per-host delay, backoff) | done, tested |
| Config-driven HTML and JSON extractors | done, tested on fixtures |
| `probe` tool to find selectors | done |
| Discord bot (`/watch /unwatch /watchlist /value /trend`) + background poller | done; **not yet run against real Discord** |
| Baseline trend predictor | done, tested |
| **Real selectors for Elvebredd / adoptmevalues.gg** | **TODO** (see below) |
| Gradient boosting / neural net predictor | later, needs weeks of history first |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # fill in DISCORD_TOKEN and USER_AGENT
python -m adoptme init-db
python -m pytest            # should be all green
```

Create the bot at <https://discord.com/developers/applications>, copy its token into `.env`, and invite it to a server you share with it (scope `bot` + `applications.commands`). It DMs you alerts, so you must share a server with it.

## Hooking up the real sites

The sites weren't reachable from the development sandbox, so the selectors in `config/sources.json` are blank and those sources are skipped until you fill them in:

1. `python -m adoptme probe https://adoptmevalues.gg/values` prints embedded JSON, repeated elements (likely list rows) and any API-looking URLs.
2. Fill in `config/sources.json`:
   - **Server-rendered HTML** (`"type": "html"`): set `selectors.row`, `name`, and either `value` (variant parsed from the name, e.g. "Neon Frost Dragon") or `variants` (`{"normal": css, "neon": css, "mega": css}` for one-row-per-pet tables). Optional `demand`.
   - **JSON** (`"type": "json"`): use a `mapping` block with `items_path`, `name`, `value` or `variants`, and `embedded_selector` (e.g. `script#__NEXT_DATA__`) when the JSON is inside the page.
   - If `probe` shows no data in the HTML, the site loads values by XHR: find the JSON request in your browser's Network tab and put that URL in `pages` with `"type": "json"`.
3. `python -m adoptme ingest` runs one pass without Discord. Check the output, then:
4. `python -m adoptme bot` runs the bot and polls every `POLL_MINUTES`.

`config/sources.json` is re-read every poll, so selector fixes take effect without a restart.

## Commands

- `/watch pet kind [value] [variant]`: alert when a pet drops to or below, rises to or above, or changes at all. Variants: `neon`, `mega`, `mega fr`, ... or `any`.
- `/unwatch id`, `/watchlist`
- `/value pet`: latest values across sources
- `/trend pet [variant] [days]`: baseline forecast (needs a few days of history)

Threshold alerts fire when the value *crosses* your target, not on every poll while it sits below.

## Politeness

One request per host at least `MIN_DELAY_SECONDS` apart, robots.txt respected by default, exponential backoff on 429/5xx, and a descriptive `USER_AGENT`. Keep `POLL_MINUTES` generous; values only change daily on most sites.

## Prediction roadmap

1. **Now:** least-squares trend line (`predict.py`). It's the benchmark.
2. After a few weeks of history: gradient boosting on value history, demand, and an update/event calendar.
3. Only if that leaves signal on the table: an LSTM/Transformer.

Walk-forward backtesting only (never random splits). Updates cause sudden jumps that no history-based model can foresee.

## Layout

```
src/adoptme/
  config.py        env config
  db.py            SQLite schema + queries
  http.py          polite HTTP client
  sources/         html.py, jsonapi.py, registry (__init__.py)
  ingest.py        one fetch-store-match pass
  watchlist.py     which watches fire
  predict.py       baseline forecaster
  bot.py           Discord bot + poller
  probe.py         selector discovery
config/sources.json
tests/
```

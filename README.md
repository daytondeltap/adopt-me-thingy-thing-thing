# Adopt Me value tracker

Personal-use tool that records pet values from value-list sites, DMs you on Discord when a pet you're watching changes or crosses a target, and gives a simple trend forecast.

**Sources:** Adopt Me Values is active. Elvebredd is enabled with a per-source robots.txt override, because the owner states its operator gave permission (its robots.txt disallows `/api` and paths under `/adopt-me-calculator/`). amvgg.com is excluded.

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
| Adopt Me Values ingest | Verified against its public pet list. Covers the initial batch of pets and available variants in that batch. |
| Elvebredd ingest | Verified live with 9,636 explicit values across 803 pets. Uses potion-specific fields from `/adopt-me-calculator` and skips eggs and pet wear. |
| Web dashboard | Search, source filter, and charts from a local JSON export. |
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

## Record values and open the dashboard

```bash
python -m adoptme ingest
python -m adoptme export-dashboard adoptme-dashboard.json
```

Open the [GitHub Pages dashboard](https://daytondeltap.github.io/adopt-me-thingy-thing-thing/) and select the exported file. You can also serve it locally with `python -m http.server --directory docs 8000` and open <http://localhost:8000>. The dashboard reads the file in the browser. The export contains pet history only, excluding Discord users, watchlists, and alerts. Keep the export and SQLite database out of the published directory.

Adopt Me Values is read from the embedded data on its public pets list. It records the initial set of pets, with normal, neon, and mega potion variants where present. Values use the source's Frost scale. Full-catalog pagination is unverified. To collect history and receive alerts, run `python -m adoptme bot` on a machine that stays on. GitHub Pages serves the dashboard, while polling and Discord run on that machine.

GitHub Pages publishing source is `main` → `/docs` (Deploy from a branch). If Pages is off, select that source in [Settings → Pages](https://github.com/daytondeltap/adopt-me-thingy-thing-thing/settings/pages).

## Adding an allowed source

Use `python -m adoptme probe <url>` to inspect an allowed public value page. In `config/sources.json`, an `html` source takes `selectors.row`, `name`, and either `value` or a `variants` map, plus optional `demand`. A `json` source takes a `mapping` block with `items_path`, `name`, and either `value` or `variants`. For JSON embedded in HTML, use `embedded_selector`. The bot reloads configuration every poll.

## Commands

- `/watch pet kind [value] [variant]`: alert when a pet drops to or below, rises to or above, or changes at all. Variants: `neon`, `mega`, `mega fr`, ... or `any`.
- `/unwatch id`, `/watchlist`
- `/value pet`: latest values across sources
- `/trend pet [variant] [days]`: baseline forecast (needs a few days of history)

Threshold alerts fire when the value *crosses* your target, not on every poll while it sits below. A possible source-wide rebase is logged and suppresses that source’s alerts for the poll while preserving its recorded values. Trend forecasts are calculated independently for each source. Existing Elvebredd snapshots with ambiguous potion variants are retained under `elvebredd_legacy`.

## Politeness

One request per host at least `MIN_DELAY_SECONDS` apart, robots.txt respected by default (a source can opt out with `ignore_robots` in `config/sources.json`, only with the site operator's permission), exponential backoff on 429/5xx, and a descriptive `USER_AGENT`. Keep `POLL_MINUTES` generous; values only change daily on most sites.

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

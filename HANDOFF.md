# Handoff brief for the next AI assistant

You are taking over a small Python project. You have not seen the earlier conversation, so everything you need is here. Read this file, then `README.md`. Last updated 2026-11-12 (commit after `6766369`).

## 1. Goal

The owner (GitHub user `daytondeltap`, timezone Asia/Bangkok, personal use only) plays the Roblox game **Adopt Me** and wants a tool that:

1. **Records pet values** from value-list websites, building a price history.
2. **Sends Discord DMs** when a watched pet changes value or crosses a target.
3. **Predicts** whether a pet's value will rise or fall. The owner asked for a neural net; see section 3 for why that comes last.

The owner prefers things that "just work" over being offered choices. Ask only when a wrong guess is costly.

## 2. Hard rules (do not break without the owner's explicit say-so)

- **Values only.** Never scrape trade ads. Never automate the Roblox or Adopt Me client (bots, auto-trading, "sniping" the game). That risks account bans. "Snipe" means a fast alert; the owner trades by hand.
- **amvgg.com is excluded.** Its Terms of Service (section 8b) ban scraping, bots, and using its value data to build datasets or bots without written permission. Do not add it unless the owner shows written permission.
- **Be polite to sites.** robots.txt is respected by default; keep a minimum delay per host, back off on 429/5xx, and poll slowly (30+ minutes; values change roughly daily).
- **robots.txt override is per source and permission-only.** `ignore_robots: true` in `config/sources.json` skips the check for that one source. It is currently set only for Elvebredd, because the owner says its operator gave permission (this is the owner's statement; it is unverified). Never make the override global, and never add it to a source without the owner stating that the operator allowed it.
- **No secrets or personal data in git.** `.env`, `data/` (SQLite) and `adoptme-dashboard.json` are gitignored. Nothing under `docs/` (published on GitHub Pages) may contain data exports.
- **Never force-push.** If a push is rejected, fetch and inspect first. The owner also commits to this repo, and a rejected push earlier turned out to be a commit that already did part of the work better.

## 3. Prediction plan (why not a neural net first)

Order: baseline trend line (exists, `predict.py`) → gradient boosting (XGBoost/LightGBM) on value history, demand, rarity, time since the last game update, an update/event calendar → a neural net (LSTM/Transformer) only if the simpler models leave signal on the table. Values move in steps when the game updates, data is small and noisy, and no history-based model can foresee updates. Use walk-forward backtests, never random splits, and show a confidence level. **There is currently almost no history, so none of this can start yet.** The sooner collection runs continuously, the sooner it can.

## 4. How the code works

Stack: Python 3.11+, SQLite, `httpx`, BeautifulSoup, `discord.py`. Single process.

```
src/adoptme/
  __main__.py   CLI: init-db, ingest, bot, probe <url>, export-dashboard <file>, trend <pet>
  config.py     env config (see .env.example)
  db.py         SQLite: items, snapshots, watchlist, alerts
  http.py       PoliteClient: robots.txt, per-host delay, backoff, per-request robots override
  ingest.py     one pass: fetch each source, store changes, match watches
  watchlist.py  decides which watches fire
  predict.py    least-squares baseline forecast
  messages.py   Discord text formatting
  bot.py        Discord slash commands + background poll loop
  dashboard.py  history export for the static dashboard
  parsing.py    number/name/variant helpers
  probe.py      page inspection helper for writing selectors
  sources/      base.py, adoptmevalues.py, elvebredd.py, html.py, jsonapi.py, __init__.py (type registry)
config/sources.json   which sources run and how
docs/                 static dashboard (GitHub Pages: main branch, /docs)
tests/                pytest; synthetic or fixture data only, no network
```

Key behaviours to preserve:
- **Variant keys:** `normal`, `neon`, `mega`, with potion suffix `_f`, `_r`, `_fr` (for example `mega_fr`).
- **Items are matched by normalized name** (lowercase, punctuation stripped). History is stored **per source**, so two sites never overwrite each other.
- **A snapshot row is written only when the value changes**, plus one heartbeat row per 24 hours. Unchanged polls store nothing.
- **Alerts:** `drop_below` / `rise_above` fire only when the value *crosses* the threshold, never while it sits past it. A first-ever sighting never fires `any_change`. A watch can fire only once per snapshot (unique constraint).
- **A failing source never blocks the others.**
- **Source types** are registered in `sources/__init__.py` (`html`, `json`, `adoptmevalues`, `elvebredd`). `config/sources.json` is re-read every poll, so config edits apply without a restart.

## 5. Source status

| Source | State |
|---|---|
| **adoptmevalues.gg** (`type: adoptmevalues`) | Active. Reads the Next.js payload embedded in `https://adoptmevalues.gg/values/pets` (`self.__next_f.push` chunks, `"initialItems"` array, items with `category == "Pets"`). Gives normal/neon/mega × potion combos (`np`, `f`, `r`, `rf`). A live pass reported in commit `d3d2608` stored 204 values for 17 pets. |
| **elvebredd** (`type: elvebredd`) | Enabled with `ignore_robots`. Reads `https://elvebredd.com/adopt-me-calculator`; finds JSON objects containing `rvalue` / `nvalue` / `mvalue` (regular / neon / mega) in the same kind of payload. **Never run against the live page.** Written from one real fragment: `"image":"/images/pets/Bat Dragon.png","rvalue":1001,"nvalue":2310,"mvalue":6550`. Name comes from `name`, else the image filename. |
| **amvgg.com** | Excluded (section 2). |

Known unknowns and risks:
- **Units differ.** adoptmevalues values are in "Frost" units (Bat Dragon 3.15, meaning relative to Frost Dragon); Elvebredd uses different numbers (Bat Dragon 1001). The two are not comparable yet. If a site rebases its unit, every value shifts at once and would trigger false alerts; nothing guards against this yet.
- **Coverage is partial.** The adoptmevalues page ships only its first batch. ChatGPT reported 24 embedded records; the earlier live pass stored 17 pets (non-pet items in the batch may explain the gap, unverified). Adding `?page=2` to the page URL returned the same batch. The page's JavaScript requests `https://adoptmevalues.gg/api/v1/items/Adoptme/pets?page=2&limit=24&sortBy=position` for more, but **nobody has seen its response**, and `/api/` may be disallowed by robots.txt.
- **Elvebredd potions:** unknown whether its values assume fly/ride.
- **The Discord bot has never run against real Discord.** It constructs and registers 5 commands (`/watch /unwatch /watchlist /value /trend`) and that is all that has been checked.

## 6. Environment limits (important if you run in a sandbox)

The previous assistant's sandbox could not reach adoptmevalues.gg or elvebredd.com (the network proxy returned 403), and could not push until the Claude GitHub App was installed (now done). If you are also blocked, do not try workarounds. Ask the owner to run a command on their own machine and paste the output. Asking a browser-enabled chatbot for page contents only works if you demand **raw HTML or raw JSON, verbatim**; summaries lose the markup you need, and such tools usually obey robots.txt and cannot see requests the page makes after it loads.

## 7. Running and verifying

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # in some sandboxes add --break-system-packages
cp .env.example .env               # set DISCORD_TOKEN and USER_AGENT
python -m adoptme init-db
python -m pytest                   # all green (50 tests at time of writing)
python -m adoptme ingest           # one live pass, prints changes, no Discord
python -m adoptme export-dashboard adoptme-dashboard.json
python -m adoptme bot              # Discord bot + poller
```

Tests use fixtures and mock transports, never the network, so a green suite says nothing about whether the live sites still parse. Only `ingest` on the owner's machine proves that.

## 8. Next tasks, in priority order

1. **Verify Elvebredd live.** Ask the owner for the output of `python -m adoptme ingest`. If it errors ("no __next_f payload" or "no usable pet values"), ask for the page's raw HTML (or the `self.__next_f.push` scripts), fix `sources/elvebredd.py`, and add a real-data test fixture. Resolve whether values assume potions.
2. **Full catalog for adoptmevalues.** Ask the owner to run `curl -s 'https://adoptmevalues.gg/api/v1/items/Adoptme/pets?page=2&limit=24&sortBy=position' | head -c 1500` and paste the result. Only if the owner confirms the operator permits reading `/api/`, add pagination to `sources/adoptmevalues.py` (stop on an empty or repeated page; reuse the existing record parser if the shape matches `initialItems`).
3. **Unit-rebase guard.** Detect a sudden uniform shift across most items in one source and suppress alerts (and flag it) rather than firing hundreds.
4. **Run the Discord bot for real** with the owner's token; fix whatever breaks.
5. **Keep it running** on an always-on machine to accumulate history. Look for a history source too: adoptmevalues pet pages draw a "Price history" chart, so a JSON endpoint behind it, if the operator allows it, could backfill weeks of data.
6. **Prediction.** After a few weeks of data: a walk-forward backtest harness, then gradient boosting, then (only if justified) a neural net.

## 9. Questions only the owner can answer

- Do both site operators' permissions cover `/api/` paths, or only the public pages?
- Is there an always-on machine or cheap server to run the bot on?
- Which Discord server should the bot join, and should alerts DM or post to a channel?
- Is cross-site comparison wanted? If so, a unit conversion between Frost units and Elvebredd's scale is needed.

## 10. History worth knowing

- An early plan included scraping trade ads and "sniping". Dropped for the Roblox ban risk and because only values were permitted.
- A CSS-selector approach for adoptmevalues (reading the card HTML) was built, then discarded when the owner's own commit `d3d2608` did it better by reading the embedded payload, which includes every variant. The card markup only shows one default-state value per pet; neon and mega are computed in the browser.
- The owner may commit directly. Always `git fetch` and inspect before pushing.

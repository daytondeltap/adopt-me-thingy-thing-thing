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

- Adopt Me Values ingest reads variant data embedded in the public `/values/pets` page. A live pass stored 204 values for 17 pets. Coverage is limited to the page's initial batch. Testing `?page=2` returned the same batch.
- Elvebredd's robots.txt restricts the calculator and API paths. The source remains disabled until there is an allowed value feed.
- The dashboard under `docs/` is static. `python -m adoptme export-dashboard adoptme-dashboard.json` exports pet history for browser-local import. See the README for GitHub Pages setup.
- SQLite storage, alerts, and the least-squares baseline are present. Discord has yet to be tested with a real server. No gradient boosting or neural net has been trained.

## 4. Next steps

1. Verify bot commands and DM delivery with the owner's Discord app. Run the bot on an always-on machine to build history.
2. Find an allowed Elvebredd value feed and a public mechanism for full-catalog coverage on Adopt Me Values before extending collection.
3. Once enough history exists, run walk-forward backtests before adding more complex models.

## 5. Operational notes

Variant keys include `normal`, `neon`, `mega`, and potion suffixes such as `mega_fr`. The first sighting does not fire a change alert. Keep `.env`, SQLite data, and personal dashboard exports out of commits and the Pages directory. See the README for setup and commands.

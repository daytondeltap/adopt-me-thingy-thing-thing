from __future__ import annotations

import argparse
import logging

from dotenv import load_dotenv

from . import db
from .config import Config
from .http import PoliteClient


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Config.from_env()

    parser = argparse.ArgumentParser(prog="adoptme", description="Adopt Me value tracker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db", help="create the SQLite database")
    sub.add_parser("ingest", help="run one ingest pass and print changes (no Discord)")
    sub.add_parser("bot", help="run the Discord bot with the background poller")
    p_probe = sub.add_parser("probe", help="inspect a page to find selectors")
    p_probe.add_argument("url")
    p_trend = sub.add_parser("trend", help="print a trend forecast from stored history")
    p_trend.add_argument("pet")
    p_trend.add_argument("--variant", default="normal")
    p_trend.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    if args.cmd == "init-db":
        with db.session(cfg.db_path):
            pass
        print(f"database ready at {cfg.db_path}")
    elif args.cmd == "ingest":
        from .ingest import run_once
        from .messages import format_alert
        from .sources import load_sources

        client = PoliteClient(cfg.user_agent, cfg.min_delay_seconds, cfg.respect_robots)
        try:
            sources = load_sources(cfg.sources_config, client)
            if not sources:
                raise SystemExit("no configured sources; fill in config/sources.json (see `probe`)")
            with db.session(cfg.db_path) as conn:
                changes, alerts = run_once(conn, sources)
            print(f"{len(changes)} value change(s), {len(alerts)} alert(s)")
            for a in alerts:
                print(" ", format_alert(a))
        finally:
            client.close()
    elif args.cmd == "bot":
        from .bot import run

        run(cfg)
    elif args.cmd == "probe":
        from .probe import probe

        client = PoliteClient(cfg.user_agent, cfg.min_delay_seconds, cfg.respect_robots)
        try:
            print(probe(client, args.url))
        finally:
            client.close()
    elif args.cmd == "trend":
        from .messages import format_forecast
        from .parsing import normalize_variant_input
        from .predict import forecast

        variant = normalize_variant_input(args.variant)
        variant = "normal" if variant == "any" else variant
        with db.session(cfg.db_path) as conn:
            series = db.history(conn, args.pet, variant, days=90)
        print(format_forecast(args.pet, variant, forecast(series, args.days), args.days))


if __name__ == "__main__":
    main()

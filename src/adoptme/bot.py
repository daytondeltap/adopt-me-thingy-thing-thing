"""Discord bot: slash commands for watchlists plus a background ingest loop."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import tasks

from . import db
from .config import Config
from .http import PoliteClient
from .ingest import run_once
from .messages import format_alert, format_forecast, format_values
from .models import Alert
from .parsing import normalize_variant_input
from .predict import forecast
from .sources import load_sources

log = logging.getLogger(__name__)

KIND_CHOICES = [
    app_commands.Choice(name="drops to or below a value", value="drop_below"),
    app_commands.Choice(name="rises to or above a value", value="rise_above"),
    app_commands.Choice(name="any change", value="any_change"),
]


class TrackerBot(discord.Client):
    def __init__(self, cfg: Config) -> None:
        super().__init__(intents=discord.Intents.default())
        self.cfg = cfg
        self.tree = app_commands.CommandTree(self)
        self._poll_loop = tasks.loop(minutes=cfg.poll_minutes)(self._poll)
        self._register_commands()

    # -- lifecycle --

    async def setup_hook(self) -> None:
        await self.tree.sync()
        self._poll_loop.start()

    async def on_ready(self) -> None:
        log.info("logged in as %s", self.user)

    # -- ingest loop --

    def _ingest_sync(self) -> list[Alert]:
        client = PoliteClient(
            self.cfg.user_agent,
            min_delay=self.cfg.min_delay_seconds,
            respect_robots=self.cfg.respect_robots,
        )
        try:
            sources = load_sources(self.cfg.sources_config, client)  # re-read so edits apply
            if not sources:
                log.warning("no configured sources; nothing to ingest")
                return []
            with db.session(self.cfg.db_path) as conn:
                _, alerts = run_once(conn, sources)
            return alerts
        finally:
            client.close()

    async def _poll(self) -> None:
        try:
            alerts = await asyncio.to_thread(self._ingest_sync)
        except Exception:
            log.exception("ingest pass failed")
            return
        for alert in alerts:
            await self._deliver(alert)

    async def _deliver(self, alert: Alert) -> None:
        text = format_alert(alert)
        try:
            user = await self.fetch_user(int(alert.watch.user_id))
            await user.send(text)
            return
        except (discord.Forbidden, discord.HTTPException) as exc:
            log.warning("DM to %s failed (%s); trying channel", alert.watch.user_id, exc)
        if self.cfg.alert_channel_id:
            channel = self.get_channel(self.cfg.alert_channel_id)
            if channel is not None:
                await channel.send(f"<@{alert.watch.user_id}> {text}")

    # -- commands --

    def _register_commands(self) -> None:
        tree = self.tree
        db_path = self.cfg.db_path

        async def pet_autocomplete(_: discord.Interaction, current: str):
            def lookup() -> list[str]:
                with db.session(db_path) as conn:
                    return db.search_item_names(conn, current)
            names = await asyncio.to_thread(lookup)
            return [app_commands.Choice(name=n, value=n) for n in names]

        @tree.command(name="watch", description="Get a DM when a pet's value changes or crosses a target")
        @app_commands.describe(
            pet="Pet name",
            kind="When to alert",
            value="Target value (needed for drops/rises)",
            variant="e.g. neon, mega, mega fr, or any (default)",
        )
        @app_commands.choices(kind=KIND_CHOICES)
        @app_commands.autocomplete(pet=pet_autocomplete)
        async def watch(
            interaction: discord.Interaction,
            pet: str,
            kind: app_commands.Choice[str],
            value: float | None = None,
            variant: str = "any",
        ) -> None:
            variant_key = normalize_variant_input(variant)

            def work():
                with db.session(db_path) as conn:
                    return db.add_watch(conn, str(interaction.user.id), pet, variant_key, kind.value, value)

            try:
                w = await asyncio.to_thread(work)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            await interaction.response.send_message(
                f"Watching **{w.display_name}** ({w.variant}) · {kind.name}"
                + (f" {value:g}" if value is not None else "")
                + f". Watch #{w.id}.",
                ephemeral=True,
            )

        @tree.command(name="unwatch", description="Remove a watch by its number")
        async def unwatch(interaction: discord.Interaction, watch_id: int) -> None:
            def work() -> bool:
                with db.session(db_path) as conn:
                    return db.remove_watch(conn, str(interaction.user.id), watch_id)

            ok = await asyncio.to_thread(work)
            await interaction.response.send_message(
                f"Removed watch #{watch_id}." if ok else f"No watch #{watch_id} of yours.", ephemeral=True
            )

        @tree.command(name="watchlist", description="Show your active watches")
        async def watchlist(interaction: discord.Interaction) -> None:
            def work():
                with db.session(db_path) as conn:
                    return db.list_watches(conn, str(interaction.user.id))

            watches = await asyncio.to_thread(work)
            if not watches:
                await interaction.response.send_message("You aren't watching anything yet.", ephemeral=True)
                return
            lines = [
                f"#{w.id} **{w.display_name}** ({w.variant}) · {w.kind}"
                + (f" {w.threshold:g}" if w.threshold is not None else "")
                for w in watches
            ]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)

        @tree.command(name="value", description="Latest recorded value for a pet")
        @app_commands.autocomplete(pet=pet_autocomplete)
        async def value_cmd(interaction: discord.Interaction, pet: str) -> None:
            def work():
                with db.session(db_path) as conn:
                    return db.latest_values(conn, pet)

            rows = await asyncio.to_thread(work)
            await interaction.response.send_message(format_values(pet, rows))

        @tree.command(name="trend", description="Simple trend forecast from recorded history")
        @app_commands.describe(pet="Pet name", variant="e.g. neon, mega fr (default normal)", days="Forecast horizon")
        @app_commands.autocomplete(pet=pet_autocomplete)
        async def trend(
            interaction: discord.Interaction, pet: str, variant: str = "normal", days: int = 7
        ) -> None:
            variant_key = normalize_variant_input(variant)
            variant_key = "normal" if variant_key == "any" else variant_key

            def work():
                with db.session(db_path) as conn:
                    return db.history(conn, pet, variant_key, days=90)

            series = await asyncio.to_thread(work)
            await interaction.response.send_message(
                format_forecast(pet, variant_key, forecast(series, days), days)
            )


def run(cfg: Config) -> None:
    if not cfg.discord_token:
        raise SystemExit("DISCORD_TOKEN is not set (copy .env.example to .env and fill it in)")
    TrackerBot(cfg).run(cfg.discord_token, log_handler=None)

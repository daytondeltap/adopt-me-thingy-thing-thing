from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    discord_token: str
    alert_channel_id: int | None
    db_path: str
    poll_minutes: int
    min_delay_seconds: float
    respect_robots: bool
    user_agent: str
    sources_config: str

    @classmethod
    def from_env(cls) -> "Config":
        channel = os.environ.get("DISCORD_ALERT_CHANNEL_ID", "").strip()
        return cls(
            discord_token=os.environ.get("DISCORD_TOKEN", "").strip(),
            alert_channel_id=int(channel) if channel else None,
            db_path=os.environ.get("DB_PATH", "data/adoptme.db"),
            poll_minutes=max(5, int(os.environ.get("POLL_MINUTES", "30"))),
            min_delay_seconds=max(1.0, float(os.environ.get("MIN_DELAY_SECONDS", "5"))),
            respect_robots=_bool(os.environ.get("RESPECT_ROBOTS"), True),
            user_agent=os.environ.get(
                "USER_AGENT", "adoptme-tracker/0.1 (personal use)"
            ),
            sources_config=os.environ.get("SOURCES_CONFIG", "config/sources.json"),
        )

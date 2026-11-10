from __future__ import annotations

from dataclasses import dataclass

VARIANTS = ("normal", "neon", "mega")


@dataclass(frozen=True)
class ValueRecord:
    """One scraped value for one pet/variant from one source."""

    source: str
    name: str
    category: str
    variant: str  # e.g. "normal", "neon", "mega_fr", "normal_f"
    value: float | None
    demand: str | None = None


@dataclass(frozen=True)
class Change:
    """A new snapshot that differs from the previous one for the same source/variant."""

    snapshot_id: int
    source: str
    name_norm: str
    display_name: str
    variant: str
    value: float
    prev_value: float | None


@dataclass(frozen=True)
class Watch:
    id: int
    user_id: str
    name_norm: str
    display_name: str
    variant: str  # "any" or a variant key
    kind: str  # any_change | drop_below | rise_above
    threshold: float | None


@dataclass(frozen=True)
class Alert:
    watch: Watch
    change: Change

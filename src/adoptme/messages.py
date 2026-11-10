"""Plain-text formatting for Discord messages (kept free of discord imports)."""

from __future__ import annotations

from .models import Alert
from .predict import Forecast


def variant_label(variant: str) -> str:
    base, _, flags = variant.partition("_")
    words = [] if base == "normal" else [base]
    if flags:
        words.append({"f": "fly", "r": "ride", "fr": "fly ride"}.get(flags, flags))
    return " ".join(words) if words else "normal"


def _num(x: float) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def format_alert(alert: Alert) -> str:
    c, w = alert.change, alert.watch
    pet = f"{c.display_name} ({variant_label(c.variant)})"
    if c.prev_value is None:
        move = f"is now **{_num(c.value)}**"
    else:
        arrow = "📈" if c.value > c.prev_value else "📉"
        move = f"{arrow} moved {_num(c.prev_value)} → **{_num(c.value)}**"
    if w.kind == "drop_below":
        why = f"dropped to or below your {_num(w.threshold)} target"
    elif w.kind == "rise_above":
        why = f"rose to or above your {_num(w.threshold)} target"
    else:
        why = "value changed"
    return f"**{pet}** {move} on {c.source} ({why}). Watch #{w.id}"


def format_values(name: str, rows) -> str:
    if not rows:
        return f"No values recorded for **{name}** yet."
    lines = [f"**{rows[0]['display_name']}**"]
    for r in rows:
        demand = f" · demand: {r['demand']}" if r["demand"] else ""
        lines.append(f"- {variant_label(r['variant'])}: **{_num(r['value'])}** ({r['source']}{demand})")
    return "\n".join(lines)


def format_forecast(name: str, variant: str, f: Forecast, horizon_days: int) -> str:
    label = f"{name} ({variant_label(variant)})"
    if f.direction == "insufficient_data":
        return (f"Not enough history for **{label}** yet ({f.points} data points). "
                "Trends need a few days of tracking.")
    sign = "+" if (f.expected_change_pct or 0) >= 0 else ""
    return (f"**{label}** looks **{f.direction}**: about {sign}{f.expected_change_pct}% over "
            f"{horizon_days} days (confidence {f.confidence:.0%}, {f.points} points). "
            "This is a simple trend line, not a guarantee; updates can move values suddenly.")

"""Helpers shared between the model and the management commands."""

from __future__ import annotations

from django.utils.translation import gettext


def format_duration(seconds: int) -> str:
    """Render a duration as a coarse human string, e.g. ``2 days 3 h 5 min``.

    Only the units that are actually present are shown. Zero and negative
    inputs render as ``0 sec`` — callers pass remaining time, and a window that
    has already elapsed has none left rather than a negative amount.
    """
    seconds = max(0, int(seconds))

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(gettext("%(n)d days") % {"n": days})
    if hours > 0:
        parts.append(gettext("%(n)d h") % {"n": hours})
    if minutes > 0:
        parts.append(gettext("%(n)d min") % {"n": minutes})
    if secs > 0 or not parts:
        parts.append(gettext("%(n)d sec") % {"n": secs})

    return " ".join(parts)

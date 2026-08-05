"""Helpers shared by the ``*_countdown`` management commands.

Django's ``find_commands()`` skips modules whose name starts with ``_``, so this
module can live beside the commands without becoming one.
"""

from __future__ import annotations

import sys
from datetime import datetime

from django.contrib.sites.models import Site
from django.core.management.base import CommandError
from django.utils import timezone


def format_when(dt: datetime) -> str:
    """Render a datetime in local time, with its zone, for operator output."""
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def is_interactive() -> bool:
    """Whether both ends of the terminal are attached, so prompting can work."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def ask(prompt: str, default: str | None = None) -> str:
    """Prompt for a line of input, falling back to ``default``.

    A closed stdin yields the default rather than raising, so a command that
    reaches a prompt in a pipeline degrades instead of crashing.
    """
    shown = f"{prompt} [{default}]: " if default is not None else f"{prompt}: "
    try:
        raw = input(shown)
    except EOFError:
        return default or ""
    return raw.strip() or (default or "")


def resolve_site(site_id: int | None) -> Site:
    """Return the named ``Site``, or the current one when ``site_id`` is ``None``."""
    if site_id is not None:
        try:
            return Site.objects.get(pk=site_id)
        except Site.DoesNotExist as exc:
            raise CommandError(f"Site with id={site_id} does not exist") from exc
    try:
        return Site.objects.get_current()
    except Site.DoesNotExist as exc:
        raise CommandError(
            "No current Site — set SITE_ID and run `migrate sites`, "
            "or pass --site-id."
        ) from exc

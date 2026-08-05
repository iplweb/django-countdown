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

from django_countdown.models import SiteCountdown

# Machine-readable phase keys. Also the ``phase`` values in ``show_countdown
# --json``, so treat them as public API once released.
PHASE_UNSCHEDULED = "unscheduled"
PHASE_BANNER = "banner"
PHASE_BLOCKED_INDEFINITE = "blocked_indefinite"
PHASE_FINISHED = "finished"
PHASE_BLOCKED = "blocked"


def classify(countdown: SiteCountdown, now: datetime | None = None) -> str:
    """Return the phase a countdown is in, as one of the ``PHASE_*`` constants.

    Evaluated as a cascade — the first match wins — because the conditions are
    not disjoint. ``clean()`` only compares ``maintenance_until`` against
    ``countdown_time``, and only when both are set, so a row with no
    ``countdown_time`` and a past ``maintenance_until`` is reachable through the
    admin and satisfies more than one condition below.

    ``now`` is injectable so a caller can re-check a guard against a fresh clock
    after an interactive prompt without re-reading the row.
    """
    now = now or timezone.now()

    if countdown.countdown_time is None:
        return PHASE_UNSCHEDULED
    if now < countdown.countdown_time:
        return PHASE_BANNER
    if countdown.maintenance_until is None:
        return PHASE_BLOCKED_INDEFINITE
    if now >= countdown.maintenance_until:
        return PHASE_FINISHED
    return PHASE_BLOCKED


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


def add_target_arguments(parser, *, allow_all: bool) -> None:
    """Add the target-selection flags shared by the countdown commands."""
    parser.add_argument(
        "--site-id",
        type=int,
        help="Act on this site only (default: SITE_ID from settings).",
    )
    if allow_all:
        parser.add_argument(
            "--all",
            action="store_true",
            help="Act on every site's countdown, not just the current one.",
        )


def resolve_targets(options, *, default_all: bool):
    """Return the countdowns a command should act on.

    ``default_all`` is the command's disposition when no flag is given: the
    incident tools (``stop``, ``show``) sweep every site, while the tools that
    edit a schedule stay on the current one unless told otherwise.
    """
    site_id = options.get("site_id")
    want_all = options.get("all", False)

    if site_id is not None and want_all:
        raise CommandError("--site-id and --all are mutually exclusive.")

    if site_id is not None:
        # Resolve first so an unknown id is an error rather than an empty result.
        return SiteCountdown.objects.filter(site=resolve_site(site_id))
    if want_all or default_all:
        return SiteCountdown.objects.all()
    return SiteCountdown.objects.filter(site=resolve_site(None))


def confirm(*, noinput: bool, prompt: str) -> bool:
    """Ask permission to proceed, defaulting to no.

    Refuses to assume consent when there is nobody to ask: a non-TTY run without
    ``--noinput`` is an error naming the flag that would have made the intent
    explicit.
    """
    if noinput:
        return True
    if not is_interactive():
        raise CommandError(
            "stdin is not a TTY — pass --noinput to proceed without confirmation."
        )
    return ask(prompt, "N").strip().lower() in {"y", "yes"}


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

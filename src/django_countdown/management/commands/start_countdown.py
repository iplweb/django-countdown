"""``manage.py start_countdown`` — schedule a maintenance window.

Interactive by default; pass ``--banner``/``--service``/``--message`` to skip
prompts. Service mode can be ``indefinite`` to keep the site blocked until an
admin removes the countdown.

Examples::

    manage.py start_countdown
    manage.py start_countdown --banner +5m --service +30m --message "Big upgrade"
    manage.py start_countdown --banner +1m --service indefinite --noinput
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta

from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from django_countdown.models import SiteCountdown

INDEFINITE_TOKENS = {"indefinite", "indefinitely", "forever", "inf", "infinite"}

# Default suggestions shown in interactive prompts.
DEFAULT_BANNER = "+5m"
DEFAULT_SERVICE = "+5m"
DEFAULT_MESSAGE = "Scheduled maintenance"

# +<int><unit> with optional whitespace; units accept English shorthand.
_RELATIVE_RE = re.compile(
    r"""^\+?\s*
        (?P<value>\d+)
        \s*
        (?P<unit>s|sec|secs|second|seconds
              |m|min|mins|minute|minutes
              |h|hr|hrs|hour|hours
              |d|day|days)?
        $
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_relative(text: str) -> timedelta:
    """Parse a ``+<N>[unit]`` string into a :class:`~datetime.timedelta`.

    Unit defaults to minutes. Returns a positive ``timedelta``.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("empty duration")
    m = _RELATIVE_RE.match(text)
    if not m:
        raise ValueError(
            f"can't parse {text!r} as a duration. "
            "Use +<N>[s|m|h|d], e.g. +5m, +1h, +2d."
        )
    value = int(m["value"])
    unit = (m["unit"] or "m").lower()
    if unit in {"s", "sec", "secs", "second", "seconds"}:
        return timedelta(seconds=value)
    if unit in {"m", "min", "mins", "minute", "minutes"}:
        return timedelta(minutes=value)
    if unit in {"h", "hr", "hrs", "hour", "hours"}:
        return timedelta(hours=value)
    if unit in {"d", "day", "days"}:
        return timedelta(days=value)
    raise ValueError(f"unsupported unit: {unit}")


def parse_when(text: str) -> datetime | None:
    """Parse an absolute ISO timestamp ``YYYY-MM-DD HH:MM[:SS]`` or ``None``."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"can't parse {text!r} as ISO datetime") from exc
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def parse_service(text: str) -> timedelta | None:
    """Parse the service-mode argument. Returns ``None`` for indefinite mode."""
    text = (text or "").strip().lower()
    if text in INDEFINITE_TOKENS:
        return None
    return parse_relative(text)


def format_when(dt: datetime) -> str:
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M:%S %Z").strip()


class Command(BaseCommand):
    help = (
        "Start a maintenance countdown for the current site. Interactive by "
        "default. Set service to 'indefinite' to keep the site blocked forever."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--banner",
            help=(
                "How long the banner shows BEFORE the site is blocked, e.g. "
                "+5m, +1h, +2d. Or an absolute ISO datetime."
            ),
        )
        parser.add_argument(
            "--service",
            help=(
                "How long service mode lasts AFTER the banner ends. "
                "Accepts +5m / +1h / +2d, an ISO datetime, or 'indefinite' "
                "to never auto-unblock."
            ),
        )
        parser.add_argument(
            "--message",
            help="Short banner message (max 200 chars).",
        )
        parser.add_argument(
            "--long-description",
            default="",
            help="Optional longer description shown on the blocked page.",
        )
        parser.add_argument(
            "--site-id",
            type=int,
            help="Site to attach to (default: SITE_ID from settings).",
        )
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_true",
            dest="noinput",
            help="Don't prompt interactively. Requires --banner / --service.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Replace any existing countdown for the site without prompting.",
        )

    # ------------------------------------------------------------------ helpers

    def _interactive(self) -> bool:
        return sys.stdin.isatty() and sys.stdout.isatty()

    def _ask(self, prompt: str, default: str | None = None) -> str:
        if default is not None:
            shown = f"{prompt} [{default}]: "
        else:
            shown = f"{prompt}: "
        try:
            raw = input(shown)
        except EOFError:
            return default or ""
        raw = raw.strip()
        return raw or (default or "")

    def _ask_banner(self) -> timedelta | datetime:
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "How long should the banner show before the site is blocked?"
            )
        )
        self.stdout.write(
            "  Suggestions: +5m, +30m, +1h, +1d  (or an ISO datetime)"
        )
        while True:
            raw = self._ask("Banner duration", DEFAULT_BANNER)
            try:
                if "T" in raw or "-" in raw[:5]:
                    dt = parse_when(raw)
                    if dt is None:
                        raise ValueError("empty")
                    return dt
                return parse_relative(raw)
            except ValueError as exc:
                self.stderr.write(self.style.WARNING(f"  ✗ {exc}"))

    def _ask_service(self) -> timedelta | None:
        self.stdout.write("")
        self.stdout.write(
            self.style.MIGRATE_HEADING("How long should service mode last?")
        )
        self.stdout.write(
            "  Suggestions: +5m, +30m, +1h, +1d, or 'indefinitely' "
            "(site stays blocked until you remove the countdown)"
        )
        while True:
            raw = self._ask("Service duration", DEFAULT_SERVICE)
            try:
                return parse_service(raw)
            except ValueError as exc:
                self.stderr.write(self.style.WARNING(f"  ✗ {exc}"))

    def _ask_message(self) -> str:
        self.stdout.write("")
        msg = self._ask("Short banner message", DEFAULT_MESSAGE)
        return msg or DEFAULT_MESSAGE

    def _resolve_site(self, site_id: int | None) -> Site:
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

    # ----------------------------------------------------------------- handle

    def handle(self, *args, **options):
        noinput = options["noinput"]
        force = options["force"]

        site = self._resolve_site(options.get("site_id"))

        # Resolve banner end (countdown_time)
        banner_raw = options.get("banner")
        if banner_raw:
            try:
                if "T" in banner_raw or banner_raw.count("-") >= 2:
                    dt = parse_when(banner_raw)
                    if dt is None:
                        raise ValueError("empty banner")
                    countdown_time = dt
                else:
                    countdown_time = timezone.now() + parse_relative(banner_raw)
            except ValueError as exc:
                raise CommandError(f"--banner: {exc}") from exc
        elif noinput:
            raise CommandError(
                "--banner is required with --noinput. "
                "Use e.g. --banner +5m."
            )
        else:
            if not self._interactive():
                raise CommandError(
                    "stdin is not a TTY — pass --banner explicitly or use a TTY."
                )
            banner_value = self._ask_banner()
            if isinstance(banner_value, datetime):
                countdown_time = banner_value
            else:
                countdown_time = timezone.now() + banner_value

        if countdown_time <= timezone.now():
            raise CommandError(
                f"Banner end ({format_when(countdown_time)}) must be in the future."
            )

        # Resolve service mode end (maintenance_until)
        service_raw = options.get("service")
        maintenance_until: datetime | None
        if service_raw:
            try:
                td = parse_service(service_raw)
            except ValueError as exc:
                raise CommandError(f"--service: {exc}") from exc
            maintenance_until = (
                None if td is None else countdown_time + td
            )
        elif noinput:
            raise CommandError(
                "--service is required with --noinput. "
                "Use e.g. --service +5m or --service indefinite."
            )
        else:
            td = self._ask_service()
            maintenance_until = None if td is None else countdown_time + td

        # Message
        message = options.get("message")
        if not message:
            if noinput:
                message = DEFAULT_MESSAGE
            else:
                message = self._ask_message()
        if len(message) > 200:
            raise CommandError("Message must be at most 200 characters.")

        long_description = options.get("long_description") or ""

        # Confirm before clobbering an existing countdown
        existing = SiteCountdown.objects.filter(site=site).first()
        if existing and not force:
            if noinput:
                raise CommandError(
                    f"A countdown already exists for {site.domain}. "
                    "Pass --force to replace it."
                )
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    f"A countdown already exists for {site.domain}:"
                )
            )
            self.stdout.write(f"  countdown_time   = {existing.countdown_time}")
            self.stdout.write(f"  maintenance_until = {existing.maintenance_until}")
            self.stdout.write(f"  message          = {existing.message}")
            answer = self._ask("Replace it? [y/N]", "N").strip().lower()
            if answer not in {"y", "yes"}:
                self.stdout.write(self.style.NOTICE("Aborted."))
                return

        # Summary + final confirm
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("About to create / replace countdown:"))
        self.stdout.write(f"  Site:              {site.domain} (id={site.pk})")
        self.stdout.write(f"  Banner shows now → {format_when(countdown_time)}")
        if maintenance_until is None:
            self.stdout.write(
                "  Service mode:      INDEFINITE "
                "(site stays blocked until you remove this countdown)"
            )
        else:
            self.stdout.write(
                f"  Service mode ends: {format_when(maintenance_until)}"
            )
        self.stdout.write(f"  Message:           {message}")

        if not noinput and not force:
            confirm = self._ask("Apply? [Y/n]", "Y").strip().lower()
            if confirm in {"n", "no"}:
                self.stdout.write(self.style.NOTICE("Aborted."))
                return

        countdown, created = SiteCountdown.objects.update_or_create(
            site=site,
            defaults={
                "countdown_time": countdown_time,
                "maintenance_until": maintenance_until,
                "message": message,
                "long_description": long_description,
            },
        )

        # Validate after save: clean() doesn't run on update_or_create, but our
        # rules also block past timestamps which we've already checked above.
        try:
            countdown.full_clean()
        except ValidationError as exc:
            countdown.delete()
            raise CommandError(f"Validation failed: {exc.message_dict}") from exc

        verb = "Created" if created else "Updated"
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"✓ {verb} countdown for {site.domain}.")
        )
        if maintenance_until is None:
            self.stdout.write(
                self.style.WARNING(
                    "  ⚠  Indefinite mode — remove the countdown via admin "
                    "or `manage.py shell` to unblock the site."
                )
            )

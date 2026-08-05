"""``manage.py show_countdown`` — report the state of every countdown.

Read-only: it never prompts, never writes, and always exits 0 — including when
a site is blocked, which is a normal state for this package rather than a
failure of the command. Monitoring should read the payload, not the exit status.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from django_countdown.utils import format_duration

from ._cli import (
    PHASE_BANNER,
    PHASE_BLOCKED,
    PHASE_BLOCKED_INDEFINITE,
    PHASE_LABELS,
    PHASE_UNSCHEDULED,
    add_target_arguments,
    classify,
    format_when,
    resolve_targets,
)


def next_transition(countdown, phase):
    """Return ``(next_event, target_datetime)`` for a phase.

    ``(None, None)`` for the phases no clock can move on: they need an operator.
    """
    if phase == PHASE_BANNER:
        return "site_closes", countdown.countdown_time
    if phase == PHASE_BLOCKED:
        return "site_reopens", countdown.maintenance_until
    return None, None


def as_iso(dt):
    """Render a datetime as a local-time ISO 8601 string, or ``None``."""
    return None if dt is None else timezone.localtime(dt).isoformat()


class Command(BaseCommand):
    help = (
        "Show the state of every site countdown: which phase it is in and how "
        "long until the next transition. Read-only; always exits 0."
    )

    def add_arguments(self, parser):
        add_target_arguments(parser, allow_all=False)
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit a JSON array on stdout and nothing else.",
        )

    def handle(self, *args, **options):
        # One clock for the whole report, so two rows can't disagree about now.
        now = timezone.now()
        countdowns = list(
            resolve_targets(options, default_all=True).select_related("site")
        )

        if options["as_json"]:
            payload = [self._as_dict(c, classify(c, now), now) for c in countdowns]
            self.stdout.write(json.dumps(payload))
            return

        if not countdowns:
            self.stdout.write("No countdowns configured.")
            return

        for index, countdown in enumerate(countdowns):
            if index:
                self.stdout.write("")
            self._write_block(countdown, classify(countdown, now), now)

    # ------------------------------------------------------------------- json

    def _as_dict(self, countdown, phase, now):
        event, target = next_transition(countdown, phase)
        return {
            "site_id": countdown.site_id,
            "domain": countdown.site.domain,
            "message": countdown.message,
            "phase": phase,
            "countdown_time": as_iso(countdown.countdown_time),
            "maintenance_until": as_iso(countdown.maintenance_until),
            "next_event": event,
            "seconds_to_next": (
                None if target is None else int((target - now).total_seconds())
            ),
        }

    # ------------------------------------------------------------------ human

    def _write_block(self, countdown, phase, now):
        self.stdout.write(f"{countdown.site.domain} — {countdown.message}")
        self.stdout.write(f"  phase   {PHASE_LABELS[phase]}")
        for line in self._detail_lines(countdown, phase, now):
            self.stdout.write(line)

    def _detail_lines(self, countdown, phase, now):
        if phase == PHASE_UNSCHEDULED:
            return ["  next    nothing scheduled for this site"]

        if phase == PHASE_BANNER:
            closes = countdown.countdown_time
            lines = [
                f"  next    site closes {format_when(closes)} "
                f"(in {format_duration((closes - now).total_seconds())})"
            ]
            reopens = countdown.maintenance_until
            if reopens is None:
                lines.append(
                    "  then    never — indefinite, run stop_countdown to reopen"
                )
            else:
                window = format_duration((reopens - closes).total_seconds())
                lines.append(
                    f"  then    site reopens {format_when(reopens)} ({window} window)"
                )
            return lines

        if phase == PHASE_BLOCKED:
            reopens = countdown.maintenance_until
            return [
                f"  next    site reopens {format_when(reopens)} "
                f"(in {format_duration((reopens - now).total_seconds())})"
            ]

        if phase == PHASE_BLOCKED_INDEFINITE:
            return [
                f"  since   site closed {format_when(countdown.countdown_time)}",
                "  next    never — run stop_countdown to reopen",
            ]

        # PHASE_FINISHED
        return [
            f"  next    none — the maintenance window is over "
            f"({format_when(countdown.maintenance_until)}); the row is stale",
            "  then    run stop_countdown to clear it",
        ]

"""Shared body of ``extend_countdown`` and ``shorten_countdown``.

The two commands are one operation with opposite signs, so they share this base
class; each concrete command supplies only its name, help text, sign, and
whether it offers ``--at-least``.

Django's ``find_commands()`` skips modules whose name starts with ``_``, so this
module can live beside the commands without becoming one.

Nothing here calls ``full_clean()``. ``SiteCountdown.clean()`` rejects any
``countdown_time`` in the past (``models.py:80-88``), so an expired row — which
is exactly the state ``extend --service`` is normally run in — could never pass
it. The guards below are therefore the only thing standing between an operator
and a corrupt row, and they have to cover both invariants ``clean()`` enforces:
``countdown_time`` in the future, and ``maintenance_until`` strictly after
``countdown_time``.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ._cli import (
    PHASE_LABELS,
    GuardViolation,
    add_target_arguments,
    apply_atomic,
    classify,
    confirm,
    format_when,
    refusal,
    resolve_targets,
)
from .start_countdown import parse_relative

MODE_BANNER = "banner"
MODE_SERVICE = "service"
MODE_AT_LEAST = "at_least"

FIELD_LABELS = {
    "countdown_time": "closes ",
    "maintenance_until": "reopens",
}

UNSCHEDULED = (
    "nothing is scheduled for this site — use start_countdown to schedule a window."
)
BANNER_OVER = (
    "the banner phase is over and the site is closed; sliding it would reopen "
    "the site and replay the banner — use start_countdown --force to "
    "reschedule, or stop_countdown to reopen now."
)
INDEFINITE_WINDOW = (
    "the maintenance window is indefinite, so it has no end to move — use "
    "start_countdown --force to give it one, or stop_countdown to reopen now."
)
WINDOW_FINISHED = (
    "the maintenance window is already over and the site has reopened; moving "
    "the end of a finished window is a state transition, not a nudge — use "
    "start_countdown --force to schedule a new window, or stop_countdown to "
    "clear the stale row."
)


class AdjustCountdownCommand(BaseCommand):
    """Move a countdown's boundaries by a relative amount.

    Subclasses set ``sign`` to ``+1`` or ``-1``; everything else is shared.
    """

    sign = 0
    verb = "adjust"
    past_tense = "Adjusted"
    offers_at_least = False

    # ------------------------------------------------------------- arguments

    def _modes(self):
        """The mode flags this command offers, as ``(flag, dest, mode)``."""
        modes = [
            ("--banner", "banner", MODE_BANNER),
            ("--service", "service", MODE_SERVICE),
        ]
        if self.offers_at_least:
            modes.append(("--at-least", "at_least", MODE_AT_LEAST))
        return modes

    def add_arguments(self, parser):
        parser.add_argument(
            "--banner",
            help=(
                f"{self.verb.capitalize()} the time until the site closes by "
                "this much, e.g. +15m. Slides the whole schedule, so the "
                "length of the maintenance window is preserved."
            ),
        )
        parser.add_argument(
            "--service",
            help=(
                f"{self.verb.capitalize()} the maintenance window by this much, "
                "e.g. +20m. Moves the moment the site reopens and nothing else."
            ),
        )
        if self.offers_at_least:
            parser.add_argument(
                "--at-least",
                dest="at_least",
                help=(
                    "Hold the window open until at least this far from now, "
                    "e.g. 5m. Writes nothing when it already reaches further, "
                    "so repeated runs absorb rather than accumulate."
                ),
            )
        add_target_arguments(parser, allow_all=True)
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_true",
            dest="noinput",
            help="Don't prompt for confirmation before writing.",
        )

    def _resolve_mode(self, options):
        """Return ``(mode, duration)``, or raise on a missing/ambiguous mode.

        Two modes at once would raise the question of whether the banner shift
        also drags the service edge, and no answer to that is obvious to a
        reader — so it is refused rather than guessed.
        """
        given = [
            (flag, mode, options.get(dest))
            for flag, dest, mode in self._modes()
            if options.get(dest)
        ]
        if len(given) != 1:
            flags = " / ".join(flag for flag, _, _ in self._modes())
            raise CommandError(f"exactly one of {flags} is required.")

        flag, mode, raw = given[0]
        try:
            # Durations are always positive; the sign lives in the command name.
            duration = parse_relative(raw)
        except ValueError as exc:
            raise CommandError(f"{flag}: {exc}") from exc
        return mode, duration

    # ----------------------------------------------------------------- guards

    def plan_for(self, row, now, *, mode, duration):
        """Return the fields to write for one row, or ``None`` to leave it be.

        Pure: it reads only ``row`` and ``now``, so ``apply_atomic`` can re-run
        it against a fresh clock inside the transaction.
        """
        if row.countdown_time is None:
            raise GuardViolation(row.site, UNSCHEDULED)
        if mode == MODE_BANNER:
            return self._plan_banner(row, now, duration)
        if mode == MODE_SERVICE:
            return self._plan_service(row, now, duration)
        return self._plan_at_least(row, now, duration)

    def _plan_banner(self, row, now, duration):
        if now >= row.countdown_time:
            raise GuardViolation(row.site, BANNER_OVER)

        closes = row.countdown_time + self.sign * duration
        if closes <= now:
            raise GuardViolation(
                row.site,
                f"the site would close {format_when(closes)}, which is not in "
                "the future — countdown_time must stay ahead of now. Use "
                "stop_countdown to close the site right away.",
            )

        fields = {"countdown_time": closes}
        # An indefinite window has no end to drag along with the banner.
        if row.maintenance_until is not None:
            fields["maintenance_until"] = row.maintenance_until + self.sign * duration
        return fields

    def _plan_service(self, row, now, duration):
        if row.maintenance_until is None:
            raise GuardViolation(row.site, INDEFINITE_WINDOW)
        if now >= row.maintenance_until:
            raise GuardViolation(row.site, WINDOW_FINISHED)

        reopens = row.maintenance_until + self.sign * duration
        # Landing before now means reopening immediately, which is
        # stop_countdown's job. Landing before countdown_time is worse: the
        # banner would count down to a closure that never happens, because at
        # countdown_time the middleware finds is_expired() and
        # is_maintenance_finished() both true and passes the request straight
        # through (middleware.py:52-54).
        floor = max(now, row.countdown_time)
        if reopens <= floor:
            raise GuardViolation(
                row.site,
                f"the window would end {format_when(reopens)}, at or before "
                f"{format_when(floor)} — a window that ends before it begins "
                "announces a closure that never happens. Use stop_countdown to "
                "reopen the site now.",
            )
        return {"maintenance_until": reopens}

    def _plan_at_least(self, row, now, duration):
        if row.maintenance_until is None:
            # "Never ends" does satisfy the floor. The preview warns that the
            # protection the operator wanted is nonetheless absent.
            return None
        if now >= row.maintenance_until:
            raise GuardViolation(row.site, WINDOW_FINISHED)

        floor = now + duration
        if row.maintenance_until >= floor:
            return None
        return {"maintenance_until": floor}

    # ----------------------------------------------------------------- handle

    def handle(self, *args, **options):
        mode, duration = self._resolve_mode(options)

        targets = resolve_targets(options, default_all=False)
        countdowns = list(targets.select_related("site"))
        if not countdowns:
            self._report_empty_target(mode)
            return

        def plan(row, at):
            return self.plan_for(row, at, mode=mode, duration=duration)

        # One clock for the whole preview, so two rows cannot disagree about
        # now. apply_atomic samples its own, later.
        now = timezone.now()
        previews, violations = [], []
        for row in countdowns:
            try:
                previews.append((row, plan(row, now)))
            except GuardViolation as exc:
                violations.append(exc)

        if violations:
            # Same wording as the write-time pass in apply_atomic, by
            # construction rather than by coincidence.
            raise refusal(violations)

        self._write_preview(previews, now, mode)

        changing = [row for row, fields in previews if fields]
        if not changing:
            # Nothing to confirm and nothing to write. Returning here also keeps
            # a covered --at-least heartbeat from failing the TTY check.
            self.stdout.write(self.style.SUCCESS("✓ Nothing to change."))
            return

        if not confirm(
            noinput=options["noinput"],
            prompt=f"Apply to {len(changing)} countdown(s)?",
        ):
            self.stdout.write(self.style.NOTICE("Aborted."))
            return

        self._report(apply_atomic(targets, plan))

    # ----------------------------------------------------------------- output

    def _report_empty_target(self, mode):
        """Nothing selected: a success for ``--at-least``, an error otherwise.

        The heartbeat recipe drops its ``|| true`` on the strength of this, so
        that every non-zero exit from it means something real. The other modes
        keep the error, because silently succeeding when there is nothing to
        move would hide a typo'd ``--site-id`` during an incident.
        """
        if mode == MODE_AT_LEAST:
            self.stdout.write(
                self.style.NOTICE(
                    "No countdown for the selected site(s) — nothing to hold."
                )
            )
            return
        raise CommandError(
            "No countdown for the selected site(s) — use start_countdown to "
            "schedule one."
        )

    def _write_preview(self, previews, now, mode):
        for row, fields in previews:
            self.stdout.write(
                f"{row.site.domain}  {PHASE_LABELS[classify(row, now)]}"
            )
            if fields:
                for name, value in fields.items():
                    self.stdout.write(
                        f"  {FIELD_LABELS[name]}  "
                        f"{format_when(getattr(row, name))} → {format_when(value)}"
                    )
                continue

            if mode == MODE_AT_LEAST and row.maintenance_until is None:
                self.stdout.write("  unchanged  the window is indefinite")
                self.stdout.write(
                    self.style.WARNING(
                        "  ⚠  this window never expires, so nothing is being "
                        "held: the site will not reopen on its own. Run "
                        "stop_countdown when the work is done."
                    )
                )
            else:
                self.stdout.write(
                    "  unchanged  already covered until "
                    f"{format_when(row.maintenance_until)}"
                )
        self.stdout.write("")

    def _report(self, written):
        self.stdout.write(
            self.style.SUCCESS(f"✓ {self.past_tense} {len(written)} countdown(s).")
        )
        for row, fields in written:
            schedule = "; ".join(
                f"{FIELD_LABELS[name].strip()} {format_when(value)}"
                for name, value in fields.items()
            )
            self.stdout.write(f"  {row.site.domain} — {schedule}")

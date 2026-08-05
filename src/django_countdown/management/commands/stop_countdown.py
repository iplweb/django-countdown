"""``manage.py stop_countdown`` — delete countdowns and reopen a blocked site.

This is the rescue command: it removes ``SiteCountdown`` rows, which is the only
way out of indefinite maintenance. It sweeps every site by default so an
operator who does not know which tenant is blocked can just run it.

Examples::

    manage.py stop_countdown
    manage.py stop_countdown --site-id 2
    manage.py stop_countdown --noinput
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from ._cli import (
    PHASE_LABELS,
    add_target_arguments,
    classify,
    confirm,
    format_when,
    resolve_targets,
)


class Command(BaseCommand):
    help = (
        "Remove maintenance countdowns, unblocking the affected sites. "
        "Acts on every site unless --site-id narrows it."
    )

    def add_arguments(self, parser):
        add_target_arguments(parser, allow_all=False)
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_true",
            dest="noinput",
            help="Don't prompt for confirmation before deleting.",
        )

    def handle(self, *args, **options):
        targets = resolve_targets(options, default_all=True)
        countdowns = list(targets.select_related("site"))

        # Before any TTY handling: nothing to delete is a success, not an error.
        if not countdowns:
            self.stdout.write(self.style.NOTICE("No countdowns to remove."))
            return

        domains = [c.site.domain for c in countdowns]

        self.stdout.write(
            self.style.WARNING(f"About to remove {len(countdowns)} countdown(s):")
        )
        for countdown in countdowns:
            # A row with no countdown_time is reachable through the admin, and
            # format_when() would choke on it — say so instead.
            when = (
                format_when(countdown.countdown_time)
                if countdown.countdown_time is not None
                else "no countdown time"
            )
            self.stdout.write(
                f"  {countdown.site.domain}  [{PHASE_LABELS[classify(countdown)]}]  "
                f"{when}  — {countdown.message}"
            )
        self.stdout.write("")

        if not confirm(
            noinput=options["noinput"],
            prompt=f"Remove {len(countdowns)} countdown(s)?",
        ):
            self.stdout.write(self.style.NOTICE("Aborted."))
            return

        with transaction.atomic():
            # Delete through the queryset, not the list built before the prompt.
            # The contract is "after this returns, nothing is blocking" — a
            # countdown that appeared while the prompt sat open has to go too,
            # or the command reports success over a site that is still closed.
            removed = targets.delete()[0]

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"✓ Removed {removed} countdown(s)."))
        for domain in domains:
            self.stdout.write(f"  {domain} — unblocked")
        if removed > len(domains):
            self.stdout.write(
                self.style.WARNING(
                    f"  ⚠  {removed - len(domains)} more appeared after the "
                    "listing above and were removed too."
                )
            )

"""``manage.py shorten_countdown`` — pull a boundary earlier.

The weakest member of the set: reopening *now* is ``stop_countdown``, and
rescheduling outright is ``start_countdown --force``. This is for the narrow
case of a window that will end earlier than announced.

Examples::

    manage.py shorten_countdown --banner +15m
    manage.py shorten_countdown --service +20m --noinput
"""

from __future__ import annotations

from ._adjust import AdjustCountdownCommand


class Command(AdjustCountdownCommand):
    help = (
        "Move a countdown's boundaries earlier for the current site. --banner "
        "brings the closure forward and slides the whole schedule; --service "
        "brings the reopening forward."
    )

    sign = -1
    verb = "shorten"
    past_tense = "Shortened"

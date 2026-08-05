"""``manage.py extend_countdown`` — push a boundary later, or hold a floor.

Acts on the current site unless ``--site-id``/``--all`` says otherwise: unlike
``stop_countdown``, this edits a schedule rather than ending an incident, and a
schedule edit fanned out across every tenant is rarely what was meant.

Examples::

    manage.py extend_countdown --banner +15m
    manage.py extend_countdown --service +20m --noinput
    manage.py extend_countdown --at-least 5m --site-id 2 --noinput
"""

from __future__ import annotations

from ._adjust import AdjustCountdownCommand


class Command(AdjustCountdownCommand):
    help = (
        "Move a countdown's boundaries later for the current site. --banner "
        "delays the closure and slides the whole schedule; --service delays "
        "the reopening; --at-least holds the window open until at least N from "
        "now, writing nothing when it already reaches further."
    )

    sign = 1
    verb = "extend"
    past_tense = "Extended"
    # The inverse — "make sure the window ends no more than N from now" — is a
    # scheduled shutdown rather than a shortening, so shorten_countdown has no
    # counterpart to this.
    offers_at_least = True

"""Tests for countdown phase classification shared by the commands."""

from datetime import timedelta

import pytest
from django.contrib.sites.models import Site
from django.utils import timezone

from django_countdown.management.commands._cli import (
    PHASE_BANNER,
    PHASE_BLOCKED,
    PHASE_BLOCKED_INDEFINITE,
    PHASE_FINISHED,
    PHASE_UNSCHEDULED,
    classify,
)
from django_countdown.models import SiteCountdown


def make(countdown_time, maintenance_until, domain="example.com"):
    """Build an unsaved row directly; ``clean()`` would reject past times."""
    site = Site.objects.get_or_create(
        domain=domain, defaults={"name": domain}
    )[0]
    return SiteCountdown(
        site=site,
        countdown_time=countdown_time,
        maintenance_until=maintenance_until,
        message="Scheduled maintenance",
    )


@pytest.mark.django_db
def test_no_countdown_time_is_unscheduled():
    assert classify(make(None, None)) == PHASE_UNSCHEDULED


@pytest.mark.django_db
def test_future_countdown_time_is_the_banner_phase():
    now = timezone.now()
    countdown = make(now + timedelta(minutes=10), now + timedelta(minutes=40))
    assert classify(countdown) == PHASE_BANNER


@pytest.mark.django_db
def test_expired_without_an_end_is_blocked_indefinitely():
    now = timezone.now()
    assert classify(make(now - timedelta(minutes=1), None)) == PHASE_BLOCKED_INDEFINITE


@pytest.mark.django_db
def test_expired_inside_the_window_is_blocked():
    now = timezone.now()
    countdown = make(now - timedelta(minutes=5), now + timedelta(minutes=25))
    assert classify(countdown) == PHASE_BLOCKED


@pytest.mark.django_db
def test_window_already_over_is_finished():
    now = timezone.now()
    countdown = make(now - timedelta(hours=2), now - timedelta(hours=1))
    assert classify(countdown) == PHASE_FINISHED


@pytest.mark.django_db
def test_unscheduled_wins_over_finished_when_both_would_match():
    """`clean()` never compares maintenance_until to now, and only compares it
    to countdown_time when both are set (models.py:89-90), so a row with no
    countdown_time and a past maintenance_until is reachable from the admin.
    It matches both conditions; the cascade must resolve it as unscheduled."""
    countdown = make(None, timezone.now() - timedelta(hours=1))
    assert classify(countdown) == PHASE_UNSCHEDULED


@pytest.mark.django_db
def test_classification_accepts_an_explicit_now():
    """Callers re-check guards against a fresh clock; the phase must follow it."""
    base = timezone.now()
    countdown = make(base + timedelta(minutes=10), base + timedelta(minutes=40))
    assert classify(countdown, now=base) == PHASE_BANNER
    assert classify(countdown, now=base + timedelta(minutes=20)) == PHASE_BLOCKED
    assert classify(countdown, now=base + timedelta(minutes=50)) == PHASE_FINISHED

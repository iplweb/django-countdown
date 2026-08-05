"""Tests for the guarded, all-or-nothing write path shared by the commands."""

from datetime import timedelta

import pytest
from django.contrib.sites.models import Site
from django.core.management.base import CommandError
from django.utils import timezone

from django_countdown.management.commands._cli import GuardViolation, apply_atomic
from django_countdown.models import SiteCountdown


@pytest.fixture
def two_countdowns(db):
    current = Site.objects.get(pk=1)
    other = Site.objects.create(domain="tenant-b.example.com", name="Tenant B")
    now = timezone.now()
    for site in (current, other):
        SiteCountdown.objects.create(
            site=site,
            countdown_time=now + timedelta(minutes=10),
            maintenance_until=now + timedelta(minutes=40),
            message=f"Maintenance for {site.domain}",
        )
    return SiteCountdown.objects.all()


def test_a_plan_returning_nothing_writes_nothing(two_countdowns):
    """The '--at-least already covered' path must not touch the row at all."""
    before = {c.pk: c.updated_at for c in two_countdowns}

    written = apply_atomic(two_countdowns, lambda row, now: None)

    assert written == []
    for countdown in SiteCountdown.objects.all():
        assert countdown.updated_at == before[countdown.pk]


def test_planned_fields_are_written_and_updated_at_advances(two_countdowns):
    target = two_countdowns.first()
    before = target.updated_at
    moved = target.maintenance_until + timedelta(minutes=15)

    apply_atomic(
        SiteCountdown.objects.filter(pk=target.pk),
        lambda row, now: {"maintenance_until": moved},
    )

    target.refresh_from_db()
    assert target.maintenance_until == moved
    assert target.updated_at > before


def test_one_guard_violation_writes_nothing_anywhere(two_countdowns):
    """A partially applied schedule change is worse than a refused one."""
    before = {c.pk: c.maintenance_until for c in two_countdowns}
    doomed = two_countdowns.last()

    def plan(row, now):
        if row.pk == doomed.pk:
            raise GuardViolation(row.site, "window would end before it starts")
        return {"maintenance_until": row.maintenance_until + timedelta(minutes=15)}

    with pytest.raises(CommandError) as excinfo:
        apply_atomic(two_countdowns, plan)

    assert doomed.site.domain in str(excinfo.value)
    assert "window would end before it starts" in str(excinfo.value)
    for countdown in SiteCountdown.objects.all():
        assert countdown.maintenance_until == before[countdown.pk]


def test_every_violation_is_reported_not_just_the_first(two_countdowns):
    """An operator fixing one site at a time would otherwise need N runs to
    discover N problems."""

    def plan(row, now):
        raise GuardViolation(row.site, "nothing is scheduled")

    with pytest.raises(CommandError) as excinfo:
        apply_atomic(two_countdowns, plan)

    message = str(excinfo.value)
    for countdown in two_countdowns:
        assert countdown.site.domain in message


def test_the_plan_sees_a_clock_sampled_inside_the_transaction(two_countdowns):
    """Guards are re-checked after the confirmation prompt, so the clock the
    plan reasons about must be read at write time, not at preview time."""
    seen = []

    apply_atomic(two_countdowns, lambda row, now: seen.append(now) or None)

    assert len(seen) == 2
    # One clock for the whole batch, so two rows cannot disagree about now.
    assert seen[0] == seen[1]
    assert (timezone.now() - seen[0]).total_seconds() < 5

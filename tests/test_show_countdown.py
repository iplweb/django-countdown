"""Tests for the ``show_countdown`` management command."""

import json
from datetime import datetime, timedelta
from io import StringIO

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import timezone

from django_countdown.management.commands._cli import (
    PHASE_BANNER,
    PHASE_BLOCKED,
    PHASE_BLOCKED_INDEFINITE,
    PHASE_FINISHED,
    PHASE_UNSCHEDULED,
    format_when,
)
from django_countdown.middleware import CountdownBlockingMiddleware
from django_countdown.models import SiteCountdown

ALL_PHASES = [
    PHASE_UNSCHEDULED,
    PHASE_BANNER,
    PHASE_BLOCKED_INDEFINITE,
    PHASE_FINISHED,
    PHASE_BLOCKED,
]

# Offsets from "now" that put a row in each phase. ``None`` means the column
# stays NULL. ``objects.create()`` skips ``clean()``, so past rows are buildable
# without a time-freezing library.
PHASE_OFFSETS = {
    PHASE_UNSCHEDULED: (None, None),
    PHASE_BANNER: (timedelta(minutes=10), timedelta(minutes=40)),
    PHASE_BLOCKED_INDEFINITE: (timedelta(hours=-1), None),
    PHASE_FINISHED: (timedelta(hours=-2), timedelta(hours=-1)),
    PHASE_BLOCKED: (timedelta(hours=-1), timedelta(hours=1)),
}


def make_row(phase, site=None, message="Scheduled maintenance"):
    """Create the countdown for ``site`` that ``classify()`` puts in ``phase``."""
    site = site or Site.objects.get_current()
    now = timezone.now()
    banner_offset, service_offset = PHASE_OFFSETS[phase]
    return SiteCountdown.objects.create(
        site=site,
        countdown_time=None if banner_offset is None else now + banner_offset,
        maintenance_until=None if service_offset is None else now + service_offset,
        message=message,
    )


def run(*args):
    """Call the command, returning its stdout."""
    out = StringIO()
    call_command("show_countdown", *args, stdout=out)
    return out.getvalue()


def run_json(*args):
    return json.loads(run("--json", *args))


# ---------- JSON payload ------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "phase, next_event",
    [
        (PHASE_UNSCHEDULED, None),
        (PHASE_BANNER, "site_closes"),
        (PHASE_BLOCKED_INDEFINITE, None),
        (PHASE_FINISHED, None),
        (PHASE_BLOCKED, "site_reopens"),
    ],
)
def test_json_reports_phase_and_next_event(phase, next_event):
    make_row(phase)

    payload = run_json()

    assert len(payload) == 1
    assert payload[0]["phase"] == phase
    assert payload[0]["next_event"] == next_event


@pytest.mark.django_db
@pytest.mark.parametrize(
    "phase", [PHASE_UNSCHEDULED, PHASE_BLOCKED_INDEFINITE, PHASE_FINISHED]
)
def test_json_seconds_to_next_is_null_without_a_transition(phase):
    make_row(phase)

    assert run_json()[0]["seconds_to_next"] is None


@pytest.mark.django_db
def test_json_seconds_to_next_counts_down_to_the_close():
    make_row(PHASE_BANNER)  # closes in 10 minutes

    seconds = run_json()[0]["seconds_to_next"]

    assert isinstance(seconds, int)
    assert 590 <= seconds <= 600


@pytest.mark.django_db
def test_json_seconds_to_next_counts_down_to_the_reopen():
    make_row(PHASE_BLOCKED)  # reopens in an hour

    seconds = run_json()[0]["seconds_to_next"]

    assert isinstance(seconds, int)
    assert 3590 <= seconds <= 3600


@pytest.mark.django_db
def test_json_carries_exactly_the_documented_keys():
    row = make_row(PHASE_BANNER)

    entry = run_json()[0]

    assert set(entry) == {
        "site_id",
        "domain",
        "message",
        "phase",
        "countdown_time",
        "maintenance_until",
        "next_event",
        "seconds_to_next",
    }
    assert entry["site_id"] == row.site_id
    assert entry["domain"] == row.site.domain
    assert entry["message"] == "Scheduled maintenance"


@pytest.mark.django_db
def test_json_timestamps_are_iso8601_and_round_trip():
    row = make_row(PHASE_BANNER)

    entry = run_json()[0]

    assert datetime.fromisoformat(entry["countdown_time"]) == row.countdown_time
    assert datetime.fromisoformat(entry["maintenance_until"]) == row.maintenance_until


@pytest.mark.django_db
def test_json_timestamps_are_null_when_unset():
    make_row(PHASE_UNSCHEDULED)

    entry = run_json()[0]

    assert entry["countdown_time"] is None
    assert entry["maintenance_until"] is None


# ---------- no countdowns -----------------------------------------------------


@pytest.mark.django_db
def test_no_countdowns_prints_one_human_line():
    output = run().strip()

    assert output
    assert len(output.splitlines()) == 1


@pytest.mark.django_db
def test_no_countdowns_is_an_empty_json_array():
    assert run_json() == []


# ---------- target selection --------------------------------------------------


# ---------- human report ------------------------------------------------------


@pytest.mark.django_db
def test_human_report_heads_each_block_with_domain_and_message():
    make_row(PHASE_BANNER, message="Big upgrade")

    assert "example.com — Big upgrade" in run()


@pytest.mark.django_db
def test_human_report_for_banner_names_the_close_then_the_reopen():
    make_row(PHASE_BANNER)

    output = run()

    assert "phase   banner showing" in output
    assert "next    site closes " in output
    assert "(in 9 min" in output  # counting down to the close
    assert "then    site reopens " in output
    assert "(30 min window)" in output


@pytest.mark.django_db
def test_human_report_for_blocked_names_the_reopen():
    make_row(PHASE_BLOCKED)

    output = run()

    assert "phase   blocked — maintenance running" in output
    assert "next    site reopens " in output
    assert "(in 59 min" in output


@pytest.mark.django_db
def test_human_report_for_blocked_indefinite_points_at_stop_countdown():
    make_row(PHASE_BLOCKED_INDEFINITE)

    output = run()

    assert "phase   blocked — indefinite maintenance" in output
    assert "next    never — run stop_countdown to reopen" in output


@pytest.mark.django_db
def test_human_report_for_finished_calls_the_row_stale():
    make_row(PHASE_FINISHED)

    output = run()

    assert "phase   finished" in output
    assert "window is over" in output
    assert "stale" in output
    assert "stop_countdown" in output


@pytest.mark.django_db
def test_human_report_for_unscheduled_says_nothing_is_scheduled():
    make_row(PHASE_UNSCHEDULED)

    output = run()

    assert "phase   unscheduled" in output
    assert "nothing scheduled" in output


@pytest.mark.django_db
def test_human_report_uses_local_timestamps():
    row = make_row(PHASE_BANNER)

    assert format_when(row.countdown_time) in run()


# ---------- target selection --------------------------------------------------


@pytest.fixture
def two_sites(db):
    current = Site.objects.get_current()
    other = Site.objects.create(domain="tenant-b.example.com", name="Tenant B")
    make_row(PHASE_BANNER, site=current, message="Current maintenance")
    make_row(PHASE_BLOCKED, site=other, message="Tenant B maintenance")
    return current, other


def test_reports_every_site_by_default(two_sites):
    assert len(run_json()) == 2


def test_site_id_limits_the_human_report(two_sites):
    _, other = two_sites

    output = run("--site-id", str(other.pk))

    assert "tenant-b.example.com" in output
    assert "example.com — Current maintenance" not in output


def test_site_id_limits_the_json_report(two_sites):
    _, other = two_sites

    payload = run_json("--site-id", str(other.pk))

    assert [entry["site_id"] for entry in payload] == [other.pk]
    assert payload[0]["phase"] == PHASE_BLOCKED


# ---------- overlapping conditions --------------------------------------------


@pytest.mark.django_db
def test_no_countdown_time_with_a_past_maintenance_end_is_unscheduled():
    """Both conditions hold; ``classify()``'s cascade must pick unscheduled."""
    SiteCountdown.objects.create(
        site=Site.objects.get_current(),
        countdown_time=None,
        maintenance_until=timezone.now() - timedelta(hours=1),
        message="Half-edited row",
    )

    entry = run_json()[0]

    assert entry["phase"] == PHASE_UNSCHEDULED
    assert entry["next_event"] is None
    assert entry["seconds_to_next"] is None
    assert "nothing scheduled" in run()


# ---------- exit status -------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("phase", ALL_PHASES)
def test_reporting_any_phase_exits_zero(phase):
    """A blocked site is a normal state, not a command failure."""
    make_row(phase)

    # call_command re-raises anything the command signals; SystemExit would
    # surface here too. Reaching the asserts means the exit status was 0.
    assert call_command("show_countdown", stdout=StringIO()) is None
    assert call_command("show_countdown", "--json", stdout=StringIO()) is None


# ---------- agreement with the middleware -------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "phase, blocks",
    [
        (PHASE_UNSCHEDULED, False),
        (PHASE_BANNER, False),
        (PHASE_BLOCKED_INDEFINITE, True),
        (PHASE_FINISHED, False),
        (PHASE_BLOCKED, True),
    ],
)
def test_reported_phase_agrees_with_the_middleware(phase, blocks):
    """The report must not drift from what the middleware actually does."""
    make_row(phase)

    assert run_json()[0]["phase"] == phase

    request = RequestFactory().get("/some/page/")
    request.user = AnonymousUser()
    middleware = CountdownBlockingMiddleware(lambda r: HttpResponse(status=200))
    response = middleware(request)

    assert response.status_code == (503 if blocks else 200)

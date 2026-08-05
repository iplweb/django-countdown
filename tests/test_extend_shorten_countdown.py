"""Tests for the ``extend_countdown`` / ``shorten_countdown`` commands.

There is no freezegun here on purpose: where time has to move, ``timezone.now``
is patched with a mutable cell so the test controls the clock without pinning
down how many times the code reads it.
"""

from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpResponse
from django.urls import path
from django.utils import timezone

from django_countdown.models import SiteCountdown

MINUTE = timedelta(minutes=1)


def _open_view(request):
    return HttpResponse("open for business")


# Used by @pytest.mark.urls below; tests/urls.py only exposes /admin/, which the
# middleware exempts, so the round trip needs a normal path of its own.
urlpatterns = [path("", _open_view)]


def make_countdown(site_id=1, *, closes=None, reopens=None, message="Maintenance"):
    """Create a row directly — ``create()`` skips ``clean()``, which is the only
    way to build the past-dated states these commands are run against."""
    return SiteCountdown.objects.create(
        site_id=site_id,
        countdown_time=closes,
        maintenance_until=reopens,
        message=message,
    )


@pytest.fixture
def frozen(mocker):
    """A clock the test moves by hand. Returns the cell and the base instant."""
    base = timezone.now()
    clock = {"now": base}
    mocker.patch("django.utils.timezone.now", lambda: clock["now"])
    return clock, base


@pytest.fixture
def second_site(db):
    return Site.objects.create(domain="tenant-b.example.com", name="Tenant B")


# ---------- effects ----------------------------------------------------------


@pytest.mark.django_db
def test_extend_service_moves_the_end_of_a_running_window():
    """The row is expired, so ``full_clean()`` would reject it outright — and
    this is the state ``extend --service`` is normally run in."""
    now = timezone.now()
    row = make_countdown(closes=now - 5 * MINUTE, reopens=now + 10 * MINUTE)

    call_command("extend_countdown", "--service", "+30m", "--noinput")

    before_closes, before_reopens = row.countdown_time, row.maintenance_until
    row.refresh_from_db()
    assert row.countdown_time == before_closes
    assert row.maintenance_until == before_reopens + 30 * MINUTE


@pytest.mark.django_db
def test_extend_service_during_the_banner_phase():
    now = timezone.now()
    row = make_countdown(closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE)

    call_command("extend_countdown", "--service", "+20m", "--noinput")

    before_closes, before_reopens = row.countdown_time, row.maintenance_until
    row.refresh_from_db()
    assert row.countdown_time == before_closes
    assert row.maintenance_until == before_reopens + 20 * MINUTE


@pytest.mark.django_db
def test_extend_banner_slides_both_boundaries_and_keeps_the_window_length():
    now = timezone.now()
    row = make_countdown(closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE)
    window = row.maintenance_until - row.countdown_time

    call_command("extend_countdown", "--banner", "+15m", "--noinput")

    before_closes, before_reopens = row.countdown_time, row.maintenance_until
    row.refresh_from_db()
    assert row.countdown_time == before_closes + 15 * MINUTE
    assert row.maintenance_until == before_reopens + 15 * MINUTE
    assert row.maintenance_until - row.countdown_time == window


@pytest.mark.django_db
def test_shorten_banner_slides_both_boundaries_the_other_way():
    now = timezone.now()
    row = make_countdown(closes=now + 30 * MINUTE, reopens=now + 60 * MINUTE)
    window = row.maintenance_until - row.countdown_time

    call_command("shorten_countdown", "--banner", "+10m", "--noinput")

    before_closes, before_reopens = row.countdown_time, row.maintenance_until
    row.refresh_from_db()
    assert row.countdown_time == before_closes - 10 * MINUTE
    assert row.maintenance_until == before_reopens - 10 * MINUTE
    assert row.maintenance_until - row.countdown_time == window


@pytest.mark.django_db
def test_extend_banner_on_an_indefinite_countdown_moves_only_the_banner():
    now = timezone.now()
    row = make_countdown(closes=now + 10 * MINUTE, reopens=None)

    call_command("extend_countdown", "--banner", "+15m", "--noinput")

    before = row.countdown_time
    row.refresh_from_db()
    assert row.countdown_time == before + 15 * MINUTE
    assert row.maintenance_until is None


# ---------- guards -----------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("command", ["extend_countdown", "shorten_countdown"])
@pytest.mark.parametrize("mode", ["--banner", "--service"])
def test_an_unscheduled_row_is_refused_in_every_mode(command, mode):
    # A maintenance_until without a countdown_time is reachable through the
    # admin, and it keeps the indefinite-window guard from covering for the
    # unscheduled one on the --service path.
    row = make_countdown(
        closes=None, reopens=timezone.now() + 40 * MINUTE, message="Draft"
    )

    with pytest.raises(CommandError) as excinfo:
        call_command(command, mode, "+5m", "--noinput")

    assert "nothing is scheduled" in str(excinfo.value)
    assert "start_countdown" in str(excinfo.value)
    row.refresh_from_db()
    assert row.countdown_time is None


@pytest.mark.django_db
def test_at_least_on_an_unscheduled_row_is_refused():
    """``--at-least`` forgives an *empty* target, not a row with no schedule."""
    make_countdown(closes=None, reopens=timezone.now() + 40 * MINUTE, message="Draft")

    with pytest.raises(CommandError) as excinfo:
        call_command("extend_countdown", "--at-least", "5m", "--noinput")

    assert "nothing is scheduled" in str(excinfo.value)
    assert "start_countdown" in str(excinfo.value)


@pytest.mark.django_db
@pytest.mark.parametrize("command", ["extend_countdown", "shorten_countdown"])
def test_banner_on_an_expired_countdown_is_refused(command):
    """Sliding the banner of a closed site would reopen it and replay the
    banner — that is ``start_countdown --force`` or ``stop_countdown``."""
    now = timezone.now()
    row = make_countdown(closes=now - 5 * MINUTE, reopens=now + 30 * MINUTE)

    with pytest.raises(CommandError) as excinfo:
        call_command(command, "--banner", "+10m", "--noinput")

    assert "start_countdown --force" in str(excinfo.value)
    assert "stop_countdown" in str(excinfo.value)
    before = row.countdown_time
    row.refresh_from_db()
    assert row.countdown_time == before


@pytest.mark.django_db
def test_shorten_banner_landing_past_now_is_refused():
    now = timezone.now()
    row = make_countdown(closes=now + 5 * MINUTE, reopens=now + 60 * MINUTE)

    with pytest.raises(CommandError) as excinfo:
        call_command("shorten_countdown", "--banner", "+10m", "--noinput")

    assert "future" in str(excinfo.value)
    before_closes, before_reopens = row.countdown_time, row.maintenance_until
    row.refresh_from_db()
    assert row.countdown_time == before_closes
    assert row.maintenance_until == before_reopens


@pytest.mark.django_db
@pytest.mark.parametrize("command", ["extend_countdown", "shorten_countdown"])
def test_service_on_an_indefinite_countdown_is_refused(command):
    now = timezone.now()
    row = make_countdown(closes=now - 5 * MINUTE, reopens=None)

    with pytest.raises(CommandError) as excinfo:
        call_command(command, "--service", "+10m", "--noinput")

    assert "indefinite" in str(excinfo.value)
    assert "start_countdown --force" in str(excinfo.value)
    row.refresh_from_db()
    assert row.maintenance_until is None


@pytest.mark.django_db
def test_shorten_service_landing_at_or_before_now_is_refused():
    now = timezone.now()
    row = make_countdown(closes=now - 30 * MINUTE, reopens=now + 5 * MINUTE)

    with pytest.raises(CommandError) as excinfo:
        call_command("shorten_countdown", "--service", "+10m", "--noinput")

    assert "stop_countdown" in str(excinfo.value)
    before = row.maintenance_until
    row.refresh_from_db()
    assert row.maintenance_until == before


@pytest.mark.urls("tests.test_extend_shorten_countdown")
@pytest.mark.django_db
def test_shorten_service_landing_inside_the_banner_phase_is_refused(client, frozen):
    """The row this would write is worse than invalid: the banner counts down to
    a closure that never happens, because at ``countdown_time`` the middleware
    finds ``is_expired()`` and ``is_maintenance_finished()`` both true and lets
    every request through."""
    clock, base = frozen
    row = make_countdown(closes=base + 10 * MINUTE, reopens=base + 40 * MINUTE)

    with pytest.raises(CommandError) as excinfo:
        call_command("shorten_countdown", "--service", "+35m", "--noinput")

    assert "stop_countdown" in str(excinfo.value)
    before_closes, before_reopens = row.countdown_time, row.maintenance_until
    row.refresh_from_db()
    assert row.countdown_time == before_closes
    assert row.maintenance_until == before_reopens

    # The point of the guard: once the banner runs out the site must actually
    # close. Had the write landed, this would be 200.
    clock["now"] = base + 20 * MINUTE
    assert client.get("/").status_code == 503


@pytest.mark.django_db
@pytest.mark.parametrize(
    "command, mode, duration",
    [
        ("extend_countdown", "--service", "+10m"),
        ("shorten_countdown", "--service", "+10m"),
        ("extend_countdown", "--at-least", "5m"),
    ],
)
def test_a_finished_window_is_refused(command, mode, duration):
    """The site has already reopened; moving the end of a window that is over is
    a state transition, not a nudge."""
    now = timezone.now()
    row = make_countdown(closes=now - 60 * MINUTE, reopens=now - 5 * MINUTE)

    with pytest.raises(CommandError) as excinfo:
        call_command(command, mode, duration, "--noinput")

    assert "start_countdown --force" in str(excinfo.value)
    before = row.maintenance_until
    row.refresh_from_db()
    assert row.maintenance_until == before


# ---------- argument handling ------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("command", ["extend_countdown", "shorten_countdown"])
def test_no_mode_flag_is_an_error(command):
    now = timezone.now()
    make_countdown(closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE)

    with pytest.raises(CommandError, match="exactly one"):
        call_command(command, "--noinput")


@pytest.mark.django_db
@pytest.mark.parametrize("command", ["extend_countdown", "shorten_countdown"])
def test_two_mode_flags_together_are_an_error(command):
    now = timezone.now()
    row = make_countdown(closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE)

    with pytest.raises(CommandError, match="exactly one"):
        call_command(command, "--banner", "+5m", "--service", "+5m", "--noinput")

    before = row.countdown_time
    row.refresh_from_db()
    assert row.countdown_time == before


@pytest.mark.django_db
def test_shorten_has_no_at_least_mode():
    """Its inverse would be a scheduled shutdown, not a shortening."""
    with pytest.raises(CommandError):
        call_command("shorten_countdown", "--at-least", "5m", "--noinput")


@pytest.mark.django_db
@pytest.mark.parametrize("bad", ["nope", "-5m", "+5x", "1y"])
def test_an_unparseable_or_negative_duration_is_an_error(bad):
    now = timezone.now()
    row = make_countdown(closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE)

    with pytest.raises(CommandError, match="--service"):
        call_command("extend_countdown", service=bad, noinput=True)

    before = row.maintenance_until
    row.refresh_from_db()
    assert row.maintenance_until == before


@pytest.mark.django_db
def test_a_negative_duration_on_the_command_line_is_an_error():
    """argparse reads ``-5m`` as a flag; either way the run must not write."""
    now = timezone.now()
    make_countdown(closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE)

    with pytest.raises(CommandError):
        call_command("extend_countdown", "--service", "-5m", "--noinput")


# ---------- --at-least -------------------------------------------------------


@pytest.mark.django_db
def test_at_least_leaves_a_window_that_already_reaches_further():
    now = timezone.now()
    row = make_countdown(closes=now - 5 * MINUTE, reopens=now + 60 * MINUTE)
    before_updated, before_reopens = row.updated_at, row.maintenance_until
    out = StringIO()

    call_command("extend_countdown", "--at-least", "5m", "--noinput", stdout=out)

    row.refresh_from_db()
    assert row.maintenance_until == before_reopens
    assert row.updated_at == before_updated
    assert "already covered" in out.getvalue()


@pytest.mark.django_db
def test_at_least_raises_the_floor_when_the_window_ends_sooner(frozen):
    clock, base = frozen
    row = make_countdown(closes=base - 5 * MINUTE, reopens=base + MINUTE)

    call_command("extend_countdown", "--at-least", "10m", "--noinput")

    before_closes = row.countdown_time
    row.refresh_from_db()
    assert row.maintenance_until == base + 10 * MINUTE
    assert row.countdown_time == before_closes


@pytest.mark.django_db
def test_at_least_twice_under_a_frozen_clock_writes_only_once(frozen):
    """Frozen is the only falsifiable form of this claim: under a moving clock
    each binding run legitimately writes a new value."""
    clock, base = frozen
    row = make_countdown(closes=base - 5 * MINUTE, reopens=base + MINUTE)

    call_command("extend_countdown", "--at-least", "10m", "--noinput")

    # auto_now is frozen too, so stamp a sentinel that a second write would
    # overwrite with the frozen clock's value.
    sentinel = base - timedelta(days=1)
    SiteCountdown.objects.filter(pk=row.pk).update(updated_at=sentinel)
    out = StringIO()

    call_command("extend_countdown", "--at-least", "10m", "--noinput", stdout=out)

    row.refresh_from_db()
    assert row.maintenance_until == base + 10 * MINUTE
    assert row.updated_at == sentinel
    assert "already covered" in out.getvalue()


@pytest.mark.django_db
def test_at_least_absorbs_rather_than_accumulates(frozen, second_site):
    """A run at t0 then t1 leaves exactly what a single run at t1 leaves — the
    property the heartbeat rests on."""
    clock, base = frozen
    twice = make_countdown(closes=base - 5 * MINUTE, reopens=base + 5 * MINUTE)
    once = make_countdown(
        site_id=second_site.pk, closes=base - 5 * MINUTE, reopens=base + 5 * MINUTE
    )

    call_command("extend_countdown", "--at-least", "10m", "--noinput")

    clock["now"] = base + 3 * MINUTE
    call_command("extend_countdown", "--at-least", "10m", "--noinput")
    call_command(
        "extend_countdown",
        "--at-least",
        "10m",
        "--site-id",
        str(second_site.pk),
        "--noinput",
    )

    twice.refresh_from_db()
    once.refresh_from_db()
    assert twice.maintenance_until == base + 13 * MINUTE
    assert twice.maintenance_until == once.maintenance_until


@pytest.mark.django_db
def test_at_least_on_an_indefinite_window_warns_and_writes_nothing():
    """"Never ends" satisfies the floor, so there is nothing to do — but the
    protection the operator wanted is absent, and silence would hide that."""
    now = timezone.now()
    row = make_countdown(closes=now - 5 * MINUTE, reopens=None)
    before = row.updated_at
    out = StringIO()

    call_command("extend_countdown", "--at-least", "5m", "--noinput", stdout=out)

    row.refresh_from_db()
    assert row.maintenance_until is None
    assert row.updated_at == before
    written = out.getvalue()
    assert "never expires" in written
    assert "stop_countdown" in written


@pytest.mark.django_db
def test_at_least_on_an_empty_target_is_a_success():
    """So the heartbeat recipe can drop ``|| true`` and have every non-zero exit
    mean something real."""
    out = StringIO()

    call_command("extend_countdown", "--at-least", "5m", "--noinput", stdout=out)

    assert "No countdown" in out.getvalue()


@pytest.mark.django_db
@pytest.mark.parametrize("mode, duration", [("--banner", "+5m"), ("--service", "+5m")])
def test_an_empty_target_is_an_error_for_the_other_modes(mode, duration):
    with pytest.raises(CommandError, match="start_countdown"):
        call_command("extend_countdown", mode, duration, "--noinput")


@pytest.mark.django_db
def test_at_least_binding_during_the_banner_phase_lands_after_the_closing_time(frozen):
    clock, base = frozen
    row = make_countdown(closes=base + MINUTE, reopens=base + 2 * MINUTE)

    call_command("extend_countdown", "--at-least", "30m", "--noinput")

    row.refresh_from_db()
    assert row.maintenance_until == base + 30 * MINUTE
    assert row.maintenance_until > row.countdown_time


# ---------- scope ------------------------------------------------------------


@pytest.mark.django_db
def test_the_default_scope_is_the_current_site_only(second_site):
    """Deliberately the opposite of stop_countdown / show_countdown."""
    now = timezone.now()
    mine = make_countdown(closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE)
    theirs = make_countdown(
        site_id=second_site.pk, closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE
    )
    untouched = theirs.maintenance_until

    call_command("extend_countdown", "--service", "+10m", "--noinput")

    before = mine.maintenance_until
    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert mine.maintenance_until == before + 10 * MINUTE
    assert theirs.maintenance_until == untouched


@pytest.mark.django_db
def test_all_moves_every_row(second_site):
    now = timezone.now()
    rows = [
        make_countdown(closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE),
        make_countdown(
            site_id=second_site.pk, closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE
        ),
    ]
    before = {row.pk: row.maintenance_until for row in rows}

    call_command("extend_countdown", "--service", "+10m", "--all", "--noinput")

    for row in SiteCountdown.objects.all():
        assert row.maintenance_until == before[row.pk] + 10 * MINUTE


@pytest.mark.django_db
def test_site_id_together_with_all_is_an_error(second_site):
    with pytest.raises(CommandError, match="mutually exclusive"):
        call_command(
            "extend_countdown",
            "--service",
            "+10m",
            "--all",
            "--site-id",
            str(second_site.pk),
            "--noinput",
        )


@pytest.mark.django_db
def test_unknown_site_id_is_an_error():
    with pytest.raises(CommandError, match="does not exist"):
        call_command(
            "extend_countdown", "--service", "+10m", "--site-id", "99999", "--noinput"
        )


@pytest.mark.django_db
def test_one_bad_row_under_all_writes_nothing_anywhere(second_site):
    """A half-applied schedule change is worse than a refused one."""
    now = timezone.now()
    good = make_countdown(closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE)
    bad = make_countdown(
        site_id=second_site.pk, closes=now + 10 * MINUTE, reopens=None
    )
    before = good.maintenance_until

    with pytest.raises(CommandError) as excinfo:
        call_command("extend_countdown", "--service", "+10m", "--all", "--noinput")

    assert second_site.domain in str(excinfo.value)
    good.refresh_from_db()
    bad.refresh_from_db()
    assert good.maintenance_until == before
    assert bad.maintenance_until is None


# ---------- confirmation -----------------------------------------------------


@pytest.mark.django_db
def test_updated_at_advances_on_a_real_change():
    now = timezone.now()
    row = make_countdown(closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE)
    before = row.updated_at

    call_command("extend_countdown", "--service", "+10m", "--noinput")

    row.refresh_from_db()
    assert row.updated_at > before


@pytest.mark.django_db
def test_a_refused_confirmation_changes_nothing(mocker):
    now = timezone.now()
    row = make_countdown(closes=now + 10 * MINUTE, reopens=now + 40 * MINUTE)
    mocker.patch(
        "django_countdown.management.commands._cli.is_interactive", return_value=True
    )
    mocker.patch("django_countdown.management.commands._cli.ask", return_value="n")
    out = StringIO()

    call_command("extend_countdown", "--service", "+10m", stdout=out)

    before = row.maintenance_until
    row.refresh_from_db()
    assert row.maintenance_until == before
    assert "Aborted." in out.getvalue()


@pytest.mark.django_db
def test_a_preview_that_goes_stale_while_the_prompt_is_open_writes_nothing(
    mocker, frozen
):
    """The guard held when the operator was asked and stopped holding before they
    answered — the re-read inside the transaction is what catches that."""
    clock, base = frozen
    row = make_countdown(closes=base - 30 * MINUTE, reopens=base + MINUTE)

    mocker.patch(
        "django_countdown.management.commands._cli.is_interactive", return_value=True
    )

    def answer_slowly(prompt, default=None):
        clock["now"] = base + 2 * MINUTE  # the window ends while we deliberate
        return "y"

    mocker.patch(
        "django_countdown.management.commands._cli.ask", side_effect=answer_slowly
    )

    with pytest.raises(CommandError) as excinfo:
        call_command("extend_countdown", "--service", "+10m", stdout=StringIO())

    assert "start_countdown --force" in str(excinfo.value)
    before = row.maintenance_until
    row.refresh_from_db()
    assert row.maintenance_until == before


# ---------- integration ------------------------------------------------------


@pytest.mark.urls("tests.test_extend_shorten_countdown")
@pytest.mark.django_db
def test_extending_service_keeps_a_blocked_site_blocked_until_the_new_end(
    client, frozen
):
    clock, base = frozen
    make_countdown(closes=base - 5 * MINUTE, reopens=base + 10 * MINUTE)

    assert client.get("/").status_code == 503

    call_command("extend_countdown", "--service", "+30m", "--noinput")

    clock["now"] = base + 20 * MINUTE  # past the original end
    assert client.get("/").status_code == 503

    clock["now"] = base + 45 * MINUTE  # past the new one
    assert client.get("/").status_code == 200

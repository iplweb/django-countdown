"""Tests for the ``stop_countdown`` management command."""

from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpResponse
from django.urls import path
from django.utils import timezone

from django_countdown.management.commands._cli import (
    PHASE_BANNER,
    PHASE_LABELS,
    PHASE_UNSCHEDULED,
    format_when,
)
from django_countdown.models import SiteCountdown


@pytest.fixture
def two_sites(db):
    """The current site (id=1, pinned by tests/settings.py) plus a second one."""
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
    return current, other


@pytest.mark.django_db
def test_listing_spells_the_phase_out_for_a_human(mocker):
    """The listing is what an operator reads before confirming a deletion, so it
    must not leak the machine-readable phase key that `show_countdown --json`
    exports."""
    SiteCountdown.objects.create(
        site=Site.objects.get(pk=1),
        countdown_time=timezone.now() - timedelta(minutes=5),
        maintenance_until=None,
        message="Indefinite maintenance",
    )
    mocker.patch(
        "django_countdown.management.commands._cli.is_interactive", return_value=True
    )
    mocker.patch("django_countdown.management.commands._cli.ask", return_value="n")
    out = StringIO()

    call_command("stop_countdown", stdout=out)

    rendered = out.getvalue()
    assert "blocked_indefinite" not in rendered
    assert "blocked — indefinite maintenance" in rendered


@pytest.mark.django_db
def test_noinput_on_a_non_tty_removes_every_site(mocker, two_sites):
    """The wide default is the decision here an operator could be surprised by,
    so it is asserted directly rather than implied by the other cases."""
    mocker.patch(
        "django_countdown.management.commands._cli.is_interactive", return_value=False
    )

    call_command("stop_countdown", "--noinput", stdout=StringIO())

    assert SiteCountdown.objects.count() == 0


@pytest.mark.django_db
def test_an_empty_answer_aborts(mocker, two_sites):
    """The prompt defaults to no; pressing Enter must keep everything."""
    mocker.patch(
        "django_countdown.management.commands._cli.is_interactive", return_value=True
    )
    mocker.patch("django_countdown.management.commands._cli.ask", return_value="")
    out = StringIO()

    call_command("stop_countdown", stdout=out)

    assert SiteCountdown.objects.count() == 2
    assert "Aborted." in out.getvalue()


@pytest.mark.django_db
def test_no_countdowns_at_all_is_a_clean_no_op(mocker):
    """The empty check must run before the TTY check, so this must not raise."""
    mocker.patch(
        "django_countdown.management.commands._cli.is_interactive", return_value=False
    )
    out = StringIO()

    call_command("stop_countdown", stdout=out)

    assert SiteCountdown.objects.count() == 0
    assert "No countdown" in out.getvalue()


@pytest.mark.django_db
def test_removes_the_only_countdown():
    now = timezone.now()
    SiteCountdown.objects.create(
        site_id=1,
        countdown_time=now + timedelta(minutes=10),
        message="Maintenance",
    )

    call_command("stop_countdown", "--noinput")

    assert SiteCountdown.objects.count() == 0


def test_removes_every_site_by_default(two_sites):
    call_command("stop_countdown", "--noinput")

    assert SiteCountdown.objects.count() == 0


def test_site_id_removes_only_that_sites_countdown(two_sites):
    current, other = two_sites

    call_command("stop_countdown", "--site-id", str(other.pk), "--noinput")

    assert [c.site_id for c in SiteCountdown.objects.all()] == [current.pk]


def test_unknown_site_id_is_an_error(two_sites):
    with pytest.raises(CommandError, match="does not exist"):
        call_command("stop_countdown", "--site-id", "99999", "--noinput")

    assert SiteCountdown.objects.count() == 2


def test_site_id_without_a_countdown_does_not_fall_back_to_all(two_sites):
    """A quiet site must not be read as 'no filter, sweep everything'."""
    quiet = Site.objects.create(domain="quiet.example.com", name="Quiet")
    out = StringIO()

    call_command("stop_countdown", "--site-id", str(quiet.pk), "--noinput", stdout=out)

    assert SiteCountdown.objects.count() == 2
    assert "No countdown" in out.getvalue()


# ---------- confirmation -----------------------------------------------------


def test_non_tty_without_noinput_refuses_and_keeps_the_row(mocker, two_sites):
    mocker.patch(
        "django_countdown.management.commands._cli.is_interactive", return_value=False
    )
    with pytest.raises(CommandError, match="--noinput"):
        call_command("stop_countdown")

    assert SiteCountdown.objects.count() == 2


def test_interactive_confirmation_accepted_removes(mocker, two_sites):
    mocker.patch(
        "django_countdown.management.commands._cli.is_interactive", return_value=True
    )
    mocker.patch("django_countdown.management.commands._cli.ask", return_value="y")

    call_command("stop_countdown")

    assert SiteCountdown.objects.count() == 0


def test_interactive_confirmation_refused_keeps_everything(mocker, two_sites):
    mocker.patch(
        "django_countdown.management.commands._cli.is_interactive", return_value=True
    )
    mocker.patch("django_countdown.management.commands._cli.ask", return_value="N")
    out = StringIO()

    call_command("stop_countdown", stdout=out)

    assert SiteCountdown.objects.count() == 2
    assert "Aborted." in out.getvalue()


# ---------- output -----------------------------------------------------------


def test_output_names_the_removed_domains(two_sites):
    current, other = two_sites
    out = StringIO()

    call_command("stop_countdown", "--noinput", stdout=out)

    written = out.getvalue()
    assert "✓ Removed 2 countdown(s)." in written
    assert current.domain in written
    assert other.domain in written


def test_lists_what_will_go_before_deleting(two_sites):
    _, other = two_sites
    doomed = SiteCountdown.objects.get(site=other)
    out = StringIO()

    call_command("stop_countdown", "--noinput", stdout=out)

    written = out.getvalue()
    assert doomed.message in written
    assert format_when(doomed.countdown_time) in written
    # The label, not the key: PHASE_BANNER is "banner", which is a substring of
    # the label "banner showing", so asserting the key would pass either way.
    assert PHASE_LABELS[PHASE_BANNER] in written


@pytest.mark.django_db
def test_lists_an_unscheduled_countdown_without_a_timestamp():
    """A row with no ``countdown_time`` is reachable via the admin."""
    SiteCountdown.objects.create(site_id=1, message="Draft, never scheduled")
    out = StringIO()

    call_command("stop_countdown", "--noinput", stdout=out)

    written = out.getvalue()
    assert "Draft, never scheduled" in written
    assert PHASE_UNSCHEDULED in written
    assert SiteCountdown.objects.count() == 0


# ---------- integration: the site really reopens ------------------------------


def _open_view(request):
    return HttpResponse("open for business")


# Used by @pytest.mark.urls below; tests/urls.py only exposes /admin/, which the
# middleware exempts, so the round trip needs a normal path of its own.
urlpatterns = [path("", _open_view)]


@pytest.mark.urls("tests.test_stop_countdown")
@pytest.mark.django_db
def test_stopping_a_blocking_countdown_reopens_the_site(client):
    now = timezone.now()
    # create() skips clean(), which is what lets us build an already-elapsed row.
    SiteCountdown.objects.create(
        site_id=1,
        countdown_time=now - timedelta(minutes=5),
        maintenance_until=now + timedelta(hours=1),
        message="Down for maintenance",
    )

    assert client.get("/").status_code == 503

    call_command("stop_countdown", "--noinput")

    assert SiteCountdown.objects.count() == 0
    assert client.get("/").status_code == 200


@pytest.mark.django_db
def test_a_countdown_created_while_the_prompt_was_open_is_also_removed(mocker):
    """The command's contract is 'after this returns, nothing is blocking', not
    'the rows on screen are gone'. Deleting the pre-prompt list would leave a
    countdown that appeared mid-prompt still blocking the site."""
    now = timezone.now()
    SiteCountdown.objects.create(
        site=Site.objects.get(pk=1),
        countdown_time=now + timedelta(minutes=10),
        maintenance_until=now + timedelta(minutes=40),
        message="On screen",
    )
    latecomer = Site.objects.create(domain="late.example.com", name="Late")

    def answer_yes_but_something_changed(prompt, default=None):
        SiteCountdown.objects.create(
            site=latecomer,
            countdown_time=now + timedelta(minutes=5),
            maintenance_until=now + timedelta(minutes=20),
            message="Appeared mid-prompt",
        )
        return "y"

    mocker.patch(
        "django_countdown.management.commands._cli.is_interactive", return_value=True
    )
    mocker.patch(
        "django_countdown.management.commands._cli.ask",
        side_effect=answer_yes_but_something_changed,
    )

    call_command("stop_countdown", stdout=StringIO())

    assert SiteCountdown.objects.count() == 0

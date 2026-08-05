"""Tests for target selection and confirmation shared by the commands."""

from datetime import timedelta

import pytest
from django.contrib.sites.models import Site
from django.core.management.base import CommandError
from django.utils import timezone

from django_countdown.management.commands._cli import confirm, resolve_targets
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


def test_default_all_targets_every_countdown(two_sites):
    targets = resolve_targets({}, default_all=True)
    assert targets.count() == 2


def test_default_current_targets_only_the_current_site(two_sites):
    current, _ = two_sites
    targets = resolve_targets({}, default_all=False)
    assert [t.site_id for t in targets] == [current.pk]


def test_site_id_narrows_regardless_of_the_default(two_sites):
    _, other = two_sites
    targets = resolve_targets({"site_id": other.pk}, default_all=True)
    assert [t.site_id for t in targets] == [other.pk]


def test_all_widens_a_current_site_default(two_sites):
    targets = resolve_targets({"all": True}, default_all=False)
    assert targets.count() == 2


def test_site_id_and_all_together_are_rejected(two_sites):
    _, other = two_sites
    with pytest.raises(CommandError, match="mutually exclusive"):
        resolve_targets({"site_id": other.pk, "all": True}, default_all=False)


def test_unknown_site_id_is_an_error_not_an_empty_result(two_sites):
    """A typo must not be reported as 'nothing to do'."""
    with pytest.raises(CommandError, match="does not exist"):
        resolve_targets({"site_id": 99999}, default_all=True)


@pytest.mark.django_db
def test_a_real_site_without_a_countdown_yields_an_empty_target():
    site = Site.objects.create(domain="quiet.example.com", name="Quiet")
    assert resolve_targets({"site_id": site.pk}, default_all=True).count() == 0


# ---------- confirmation -----------------------------------------------------


def test_confirm_short_circuits_under_noinput(mocker):
    interactive = mocker.patch(
        "django_countdown.management.commands._cli.is_interactive"
    )
    assert confirm(noinput=True, prompt="Remove 1 countdown?") is True
    interactive.assert_not_called()


def test_confirm_refuses_to_guess_when_stdin_is_not_a_tty(mocker):
    mocker.patch(
        "django_countdown.management.commands._cli.is_interactive", return_value=False
    )
    with pytest.raises(CommandError, match="--noinput"):
        confirm(noinput=False, prompt="Remove 1 countdown?")


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("y", True),
        ("Y", True),
        ("yes", True),
        ("", False),
        ("n", False),
        ("nope", False),
    ],
)
def test_confirm_defaults_to_no(mocker, answer, expected):
    mocker.patch(
        "django_countdown.management.commands._cli.is_interactive", return_value=True
    )
    mocker.patch(
        "django_countdown.management.commands._cli.ask", return_value=answer or "N"
    )
    assert confirm(noinput=False, prompt="Remove 1 countdown?") is expected

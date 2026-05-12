"""Tests for the ``start_countdown`` management command."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from django_countdown.management.commands.start_countdown import (
    INDEFINITE_TOKENS,
    parse_relative,
    parse_service,
)
from django_countdown.models import SiteCountdown

# ---------- parse helpers ----------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+5m", timedelta(minutes=5)),
        ("5m", timedelta(minutes=5)),
        ("+30s", timedelta(seconds=30)),
        ("+2h", timedelta(hours=2)),
        ("+1d", timedelta(days=1)),
        ("+15", timedelta(minutes=15)),  # default unit = minutes
        ("+1 hours", timedelta(hours=1)),
        ("+10 minutes", timedelta(minutes=10)),
    ],
)
def test_parse_relative_accepts_common_forms(raw, expected):
    assert parse_relative(raw) == expected


@pytest.mark.parametrize("bad", ["", "nope", "+", "+5x", "1y", "-5m"])
def test_parse_relative_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        parse_relative(bad)


@pytest.mark.parametrize("token", sorted(INDEFINITE_TOKENS))
def test_parse_service_indefinite_tokens_return_none(token):
    assert parse_service(token) is None
    assert parse_service(token.upper()) is None


def test_parse_service_relative():
    assert parse_service("+5m") == timedelta(minutes=5)


# ---------- non-interactive integration --------------------------------------


@pytest.mark.django_db
def test_command_creates_countdown_with_indefinite_service():
    out = StringIO()
    call_command(
        "start_countdown",
        "--banner",
        "+1m",
        "--service",
        "indefinite",
        "--message",
        "Big upgrade",
        "--noinput",
        stdout=out,
    )

    countdown = SiteCountdown.objects.get()
    assert countdown.message == "Big upgrade"
    assert countdown.maintenance_until is None
    assert countdown.is_indefinite()
    assert countdown.countdown_time > timezone.now()
    assert "Indefinite mode" in out.getvalue()


@pytest.mark.django_db
def test_command_creates_countdown_with_relative_service_duration():
    call_command(
        "start_countdown",
        "--banner",
        "+1m",
        "--service",
        "+10m",
        "--message",
        "Small update",
        "--noinput",
    )

    countdown = SiteCountdown.objects.get()
    assert countdown.maintenance_until is not None
    delta = countdown.maintenance_until - countdown.countdown_time
    assert delta == timedelta(minutes=10)


@pytest.mark.django_db
def test_command_rejects_past_banner():
    with pytest.raises(CommandError, match="must be in the future"):
        # 0m → resolves to "now" which is not strictly in the future
        call_command(
            "start_countdown",
            "--banner",
            "+0m",
            "--service",
            "indefinite",
            "--noinput",
        )


@pytest.mark.django_db
def test_command_requires_banner_when_noinput():
    with pytest.raises(CommandError, match="--banner is required"):
        call_command("start_countdown", "--noinput", "--service", "+5m")


@pytest.mark.django_db
def test_command_requires_service_when_noinput():
    with pytest.raises(CommandError, match="--service is required"):
        call_command("start_countdown", "--noinput", "--banner", "+5m")


@pytest.mark.django_db
def test_command_replaces_existing_with_force():
    call_command(
        "start_countdown",
        "--banner",
        "+1m",
        "--service",
        "indefinite",
        "--message",
        "First",
        "--noinput",
    )
    call_command(
        "start_countdown",
        "--banner",
        "+1m",
        "--service",
        "+5m",
        "--message",
        "Second",
        "--noinput",
        "--force",
    )
    countdown = SiteCountdown.objects.get()
    assert countdown.message == "Second"
    assert countdown.maintenance_until is not None


@pytest.mark.django_db
def test_command_refuses_to_overwrite_without_force_in_noinput():
    call_command(
        "start_countdown",
        "--banner",
        "+1m",
        "--service",
        "indefinite",
        "--noinput",
    )
    with pytest.raises(CommandError, match="--force"):
        call_command(
            "start_countdown",
            "--banner",
            "+1m",
            "--service",
            "+5m",
            "--noinput",
        )

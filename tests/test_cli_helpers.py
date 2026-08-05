"""Tests for the helpers shared by the countdown management commands."""

import builtins
from datetime import datetime

import pytest
from django.contrib.sites.models import Site
from django.core.management.base import CommandError
from django.utils import timezone

from django_countdown.management.commands._cli import (
    ask,
    format_when,
    is_interactive,
    resolve_site,
)


def test_format_when_renders_local_time_with_zone():
    dt = timezone.make_aware(datetime(2026, 8, 5, 9, 15, 0))
    rendered = format_when(dt)
    assert rendered.startswith("2026-08-05 09:15:00")
    assert rendered.strip() == rendered


def test_ask_returns_the_typed_answer(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda prompt: "  typed  ")
    assert ask("Question", "fallback") == "typed"


def test_ask_falls_back_to_the_default_on_empty_input(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda prompt: "   ")
    assert ask("Question", "fallback") == "fallback"


def test_ask_shows_the_default_in_the_prompt(monkeypatch):
    seen = {}

    def fake_input(prompt):
        seen["prompt"] = prompt
        return ""

    monkeypatch.setattr(builtins, "input", fake_input)
    ask("Banner duration", "+5m")
    assert "[+5m]" in seen["prompt"]


def test_ask_survives_a_closed_stdin(monkeypatch):
    """A piped-in command that runs out of input must not crash the command."""

    def raise_eof(prompt):
        raise EOFError

    monkeypatch.setattr(builtins, "input", raise_eof)
    assert ask("Question", "fallback") == "fallback"


def test_is_interactive_is_false_when_stdin_is_not_a_tty(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    assert is_interactive() is False


@pytest.mark.django_db
def test_resolve_site_returns_the_named_site():
    site = Site.objects.create(domain="tenant.example.com", name="Tenant")
    assert resolve_site(site.pk) == site


@pytest.mark.django_db
def test_resolve_site_rejects_an_unknown_id():
    with pytest.raises(CommandError, match="does not exist"):
        resolve_site(99999)


@pytest.mark.django_db
def test_resolve_site_falls_back_to_the_current_site():
    """No id means SITE_ID from settings, which the test settings pin to 1."""
    assert resolve_site(None).pk == 1

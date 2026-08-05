"""Tests for the shared duration formatting helper."""

import pytest

from django_countdown.utils import format_duration


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (2 * 86400 + 3 * 3600 + 5 * 60, "2 days 3 h 5 min"),
        (86400, "1 days"),
        (3600, "1 h"),
        (90, "1 min 30 sec"),
        (45, "45 sec"),
    ],
)
def test_format_duration_joins_the_units_present(seconds, expected):
    assert format_duration(seconds) == expected


def test_format_duration_reports_seconds_when_nothing_else_is_left():
    """A bare zero still needs a unit, otherwise the string would be empty."""
    assert format_duration(0) == "0 sec"


def test_format_duration_clamps_negative_input():
    """Callers pass elapsed windows; a negative remainder is zero remaining."""
    assert format_duration(-500) == "0 sec"

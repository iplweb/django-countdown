from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _


class SiteCountdown(models.Model):
    """Maintenance countdown attached to a single :class:`Site`."""

    site = models.OneToOneField(
        Site,
        on_delete=models.CASCADE,
        verbose_name=_("Site"),
        help_text=_("Site to which this countdown applies"),
    )

    countdown_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Countdown time"),
        help_text=_("Date and time at which the site will be blocked"),
    )

    maintenance_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Maintenance end"),
        help_text=_(
            "Date and time when maintenance ends (optional). "
            "Leave empty for indefinite maintenance — the site will stay "
            "blocked until the countdown is removed."
        ),
    )

    message = models.CharField(
        max_length=200,
        verbose_name=_("Short message"),
        help_text=_("Short message shown in the page header (max 200 chars)"),
    )

    long_description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Long description"),
        help_text=_("Optional longer description shown on the blocked page"),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        verbose_name = _("Site shutdown countdown")
        verbose_name_plural = _("Site shutdown countdowns")
        ordering = ["-countdown_time"]

    def __str__(self):
        return f"{self.site.domain} - {self.message} ({self.countdown_time})"

    def is_expired(self):
        """Return whether the countdown has elapsed."""
        if self.countdown_time is None:
            return False
        return timezone.now() >= self.countdown_time

    is_expired.boolean = True
    is_expired.short_description = _("Expired?")

    def is_indefinite(self):
        """Return whether maintenance lasts indefinitely (no end time)."""
        return self.countdown_time is not None and self.maintenance_until is None

    is_indefinite.boolean = True
    is_indefinite.short_description = _("Indefinite?")

    def clean(self):
        """Reject countdown times in the past and out-of-order maintenance ends."""
        super().clean()
        if self.countdown_time and self.countdown_time <= timezone.now():
            raise ValidationError(
                {
                    "countdown_time": _(
                        "Countdown time cannot be in the past. "
                        "Pick a future date."
                    )
                }
            )
        if self.maintenance_until and self.countdown_time:
            if self.maintenance_until <= self.countdown_time:
                raise ValidationError(
                    {
                        "maintenance_until": _(
                            "Maintenance end must be later than the countdown time."
                        )
                    }
                )

    def time_remaining(self):
        """Return a human-readable string of time remaining until countdown."""
        if self.countdown_time is None:
            return gettext("Not set")
        if self.is_expired():
            return gettext("Expired")

        delta = self.countdown_time - timezone.now()
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(gettext("%(n)d days") % {"n": days})
        if hours > 0:
            parts.append(gettext("%(n)d h") % {"n": hours})
        if minutes > 0:
            parts.append(gettext("%(n)d min") % {"n": minutes})
        if seconds > 0 or not parts:
            parts.append(gettext("%(n)d sec") % {"n": seconds})

        return " ".join(parts)

    time_remaining.short_description = _("Time remaining")

    def is_maintenance_finished(self):
        """Return whether the maintenance window has ended.

        Always ``False`` for indefinite maintenance — the site stays blocked
        until an admin removes the countdown.
        """
        if self.maintenance_until is None:
            return False
        return timezone.now() >= self.maintenance_until

    is_maintenance_finished.boolean = True
    is_maintenance_finished.short_description = _("Maintenance finished?")

    def maintenance_time_remaining(self):
        """Seconds remaining until maintenance ends, or ``None`` if indefinite."""
        if self.maintenance_until is None:
            return None
        if self.is_maintenance_finished():
            return None

        delta = self.maintenance_until - timezone.now()
        return int(delta.total_seconds())

    def maintenance_duration_minutes(self):
        """Planned maintenance duration in minutes, or ``None`` if indefinite."""
        if self.maintenance_until is None or self.countdown_time is None:
            return None

        delta = self.maintenance_until - self.countdown_time
        return int(delta.total_seconds() / 60)

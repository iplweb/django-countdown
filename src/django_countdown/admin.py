from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from .models import SiteCountdown


@admin.register(SiteCountdown)
class SiteCountdownAdmin(admin.ModelAdmin):
    list_display = [
        "site",
        "message",
        "countdown_time",
        "maintenance_until",
        "is_expired",
        "is_indefinite",
        "time_remaining_display",
        "created_at",
    ]
    list_filter = ["site", "countdown_time"]
    search_fields = ["message", "long_description"]
    readonly_fields = ["created_at", "updated_at", "time_remaining_display"]

    fieldsets = [
        (
            _("Basic information"),
            {
                "fields": ["site", "countdown_time", "maintenance_until"],
                "description": _(
                    "Leave 'Maintenance end' empty to keep the site blocked "
                    "indefinitely once the countdown expires."
                ),
            },
        ),
        (
            _("Messages"),
            {
                "fields": ["message", "long_description"],
            },
        ),
        (
            _("Metadata"),
            {
                "fields": ["created_at", "updated_at", "time_remaining_display"],
                "classes": ["collapse"],
            },
        ),
    ]

    @admin.display(description=_("Time remaining"))
    def time_remaining_display(self, obj):
        """Render time-remaining as a coloured status badge."""
        if obj.countdown_time is None:
            return mark_safe(
                '<span class="admin-status--gray admin-status--bold">'
                + gettext("Not set")
                + "</span>"
            )
        elif obj.is_expired():
            return mark_safe(
                '<span class="admin-status--red admin-status--bold">'
                + gettext("Expired")
                + "</span>"
            )
        else:
            return format_html(
                '<span class="admin-status--green admin-status--bold">{}</span>',
                obj.time_remaining(),
            )

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import SiteCountdown


@admin.register(SiteCountdown)
class SiteCountdownAdmin(admin.ModelAdmin):
    list_display = [
        "site",
        "message",
        "countdown_time",
        "maintenance_until",
        "is_expired",
        "time_remaining_display",
        "created_at",
    ]
    list_filter = ["site", "countdown_time"]
    search_fields = ["message", "long_description"]
    readonly_fields = ["created_at", "updated_at", "time_remaining_display"]

    fieldsets = [
        (
            "Podstawowe informacje",
            {
                "fields": ["site", "countdown_time", "maintenance_until"],
            },
        ),
        (
            "Komunikaty",
            {
                "fields": ["message", "long_description"],
            },
        ),
        (
            "Metadane",
            {
                "fields": ["created_at", "updated_at", "time_remaining_display"],
                "classes": ["collapse"],
            },
        ),
    ]

    @admin.display(description="Pozostały czas")
    def time_remaining_display(self, obj):
        """Wyświetla pozostały czas w czytelnym formacie z kolorowym wskaźnikiem."""
        if obj.countdown_time is None:
            return mark_safe(
                '<span class="admin-status--gray admin-status--bold">'
                "Nie ustawiono</span>"
            )
        elif obj.is_expired():
            return mark_safe(
                '<span class="admin-status--red admin-status--bold">Wygasło</span>'
            )
        else:
            return format_html(
                '<span class="admin-status--green admin-status--bold">{}</span>',
                obj.time_remaining(),
            )

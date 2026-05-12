from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DjangoCountdownConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_countdown"
    verbose_name = _("Site shutdown countdown")

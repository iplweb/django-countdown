import pytest
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from django_countdown.models import SiteCountdown


@pytest.fixture
def admin_client(db):
    User = get_user_model()
    admin = User.objects.create_superuser(
        "admin",
        "admin@example.com",
        "pw",  # noqa: S106
    )
    c = Client()
    c.force_login(admin)
    return c


@pytest.mark.django_db
def test_sitecountdown_admin_changelist(admin_client):
    """The admin changelist for SiteCountdown loads without errors."""
    url = reverse("admin:django_countdown_sitecountdown_changelist")
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_sitecountdown_admin_change_view(admin_client):
    """The admin change view loads for an existing SiteCountdown."""
    site = Site.objects.get_current()
    countdown = baker.make(
        SiteCountdown,
        site=site,
        countdown_time=timezone.now() + timezone.timedelta(hours=1),
        message="Test",
    )
    url = reverse("admin:django_countdown_sitecountdown_change", args=[countdown.pk])
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_sitecountdown_admin_time_remaining_display_no_time(admin_client):
    """time_remaining_display renders gray status when countdown_time is None."""
    site = Site.objects.get_current()
    countdown = baker.make(
        SiteCountdown,
        site=site,
        countdown_time=None,
        message="Test",
    )
    from django.contrib.admin.sites import AdminSite

    from django_countdown.admin import SiteCountdownAdmin

    admin_instance = SiteCountdownAdmin(SiteCountdown, AdminSite())
    rendered = admin_instance.time_remaining_display(countdown)
    assert "Nie ustawiono" in rendered

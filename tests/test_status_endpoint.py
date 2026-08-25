"""Testy endpointu statusu odpytywanego w tle przez stronę przerwy technicznej.

Endpoint ma jedno zadanie: pozwolić przeglądarce odróżnić trzy sytuacje —
serwer działa i przerwa trwa, serwer działa i przerwa się skończyła, serwer
nie odpowiada (nginx zwraca 5xx). Dlatego zawsze odpowiada kodem 200,
a stan niesie w ciele odpowiedzi: kod 503 potrafiłby wygenerować sam proxy
i wtedy dwa pierwsze przypadki byłyby nieodróżnialne od trzeciego.
"""

import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.test import RequestFactory
from django.utils import timezone
from model_bakery import baker

from django_countdown.middleware import (
    DEFAULT_STATUS_PATH,
    CountdownBlockingMiddleware,
)
from django_countdown.models import SiteCountdown

User = get_user_model()


def call_status(path=DEFAULT_STATUS_PATH, user=None):
    """Uderz w endpoint statusu przez middleware i zwróć odpowiedź."""
    request = RequestFactory().get(path)
    if user is not None:
        request.user = user
    return CountdownBlockingMiddleware(lambda r: None).process_request(request)


def payload(response):
    return json.loads(response.content.decode("utf-8"))


@pytest.mark.django_db
def test_status_endpoint_reports_blocked_with_http_200_during_maintenance():
    """KRYTYCZNY: trwająca przerwa to 200 + blocked=true, nigdy 503.

    503 zwraca również nginx, gdy nie ma upstreamu — gdyby endpoint też go
    używał, przeglądarka nie odróżniłaby trwającej przerwy od martwego serwera.
    """
    site = Site.objects.get_current()
    baker.make(
        SiteCountdown, site=site, countdown_time=timezone.now() - timedelta(hours=1)
    )

    response = call_status()

    assert response is not None
    assert response.status_code == 200
    assert payload(response)["blocked"] is True


@pytest.mark.django_db
def test_status_endpoint_reports_unblocked_when_no_countdown_exists():
    """Brak countdownu to czysty serwer — przeglądarka może przenieść użytkownika."""
    response = call_status()

    assert response.status_code == 200
    assert payload(response)["blocked"] is False


@pytest.mark.django_db
def test_status_endpoint_reports_unblocked_after_maintenance_finished():
    """Po minięciu maintenance_until strona jest znowu dostępna."""
    site = Site.objects.get_current()
    baker.make(
        SiteCountdown,
        site=site,
        countdown_time=timezone.now() - timedelta(hours=2),
        maintenance_until=timezone.now() - timedelta(hours=1),
    )

    response = call_status()

    assert payload(response)["blocked"] is False


@pytest.mark.django_db
def test_status_endpoint_reports_unblocked_for_superuser():
    """Superuser widzi stan, który jego przeglądarka faktycznie zastanie."""
    site = Site.objects.get_current()
    baker.make(
        SiteCountdown, site=site, countdown_time=timezone.now() - timedelta(hours=1)
    )

    response = call_status(user=baker.make(User, is_superuser=True, username="admin"))

    assert payload(response)["blocked"] is False


@pytest.mark.django_db
def test_status_endpoint_carries_service_marker():
    """Marker pozwala odróżnić odpowiedź Django od strony błędu proxy."""
    response = call_status()

    assert payload(response)["service"] == "django-countdown"


@pytest.mark.django_db
def test_status_endpoint_exposes_maintenance_until():
    """Klient dostaje serwerową prawdę o końcu przerwy, nie tylko własny zegar."""
    site = Site.objects.get_current()
    maintenance_until = timezone.now() + timedelta(minutes=20)
    baker.make(
        SiteCountdown,
        site=site,
        countdown_time=timezone.now() - timedelta(minutes=5),
        maintenance_until=maintenance_until,
    )

    assert payload(call_status())["maintenance_until"] == maintenance_until.isoformat()


@pytest.mark.django_db
def test_status_endpoint_reports_null_maintenance_until_when_indefinite():
    """Przerwa bezterminowa nie ma końca do podania."""
    site = Site.objects.get_current()
    baker.make(
        SiteCountdown,
        site=site,
        countdown_time=timezone.now() - timedelta(minutes=5),
        maintenance_until=None,
    )

    assert payload(call_status())["maintenance_until"] is None


@pytest.mark.django_db
def test_status_endpoint_forbids_caching():
    """Zbuforowana odpowiedź zamroziłaby użytkownika na stronie przerwy."""
    response = call_status()

    assert "no-store" in response["Cache-Control"]


@pytest.mark.django_db
def test_status_endpoint_honours_custom_path_setting(settings):
    """Ścieżkę można przenieść, gdy domyślna koliduje z URL-ami projektu."""
    settings.DJANGO_COUNTDOWN_STATUS_PATH = "/_health/countdown/"
    site = Site.objects.get_current()
    baker.make(
        SiteCountdown, site=site, countdown_time=timezone.now() - timedelta(hours=1)
    )

    on_custom_path = call_status(path="/_health/countdown/")
    on_default_path = call_status(path=DEFAULT_STATUS_PATH)

    assert on_custom_path.status_code == 200
    assert payload(on_custom_path)["blocked"] is True
    # Domyślna ścieżka przestaje być endpointem — dostaje zwykłą blokadę.
    assert on_default_path.status_code == 503


# ============================================================================
# STRONA BLOKADY — co szablon dostaje i czego już nie robi
# ============================================================================


def render_blocked_page(path="/", **countdown_kwargs):
    """Wywołaj middleware na zablokowanej stronie i zwróć wyrenderowany HTML."""
    site = Site.objects.get_current()
    fields = {
        "countdown_time": timezone.now() - timedelta(minutes=5),
        "maintenance_until": timezone.now() + timedelta(minutes=20),
    }
    fields.update(countdown_kwargs)
    baker.make(SiteCountdown, site=site, **fields)

    request = RequestFactory().get(path)
    response = CountdownBlockingMiddleware(lambda r: None).process_request(request)
    assert response.status_code == 503
    return response.content.decode("utf-8")


@pytest.mark.django_db
def test_blocked_page_embeds_status_path_and_poll_interval():
    """Strona musi wiedzieć, gdzie i jak często pytać."""
    content = render_blocked_page()

    assert DEFAULT_STATUS_PATH in content
    assert "10" in content


@pytest.mark.django_db
def test_blocked_page_carries_the_originally_requested_url():
    """Po powrocie serwera użytkownik ma trafić tam, gdzie chciał wejść."""
    content = render_blocked_page(path="/protected/report/")

    assert "/protected/report/" in content


@pytest.mark.django_db
def test_blocked_page_never_reloads_blindly_when_timer_runs_out():
    """KRYTYCZNY: licznik nie może nawigować.

    Zegar odlicza lokalnie w przeglądarce i nie wie nic o serwerze. Gdy dojdzie
    do zera w chwili, gdy kontener jeszcze wstaje, ślepe przeładowanie wysyła
    użytkownika na stronę błędu nginksa — bez JS-a, który by dalej pytał.
    Nawigację podejmuje wyłącznie poller, po potwierdzeniu z serwera.
    """
    content = render_blocked_page()

    assert "location.reload" not in content


@pytest.mark.django_db
def test_blocked_page_never_reloads_blindly_during_indefinite_maintenance():
    """Ten sam zakaz obowiązuje przy przerwie bez podanego końca."""
    content = render_blocked_page(maintenance_until=None)

    assert "location.reload" not in content


@pytest.mark.django_db
def test_blocked_page_omits_poller_when_polling_disabled(settings):
    """Interwał 0 wyłącza odpytywanie — strona zostaje całkiem statyczna."""
    settings.DJANGO_COUNTDOWN_POLL_INTERVAL = 0

    content = render_blocked_page()

    assert DEFAULT_STATUS_PATH not in content


@pytest.mark.django_db
def test_blocked_page_resyncs_its_clock_from_the_server():
    """Przedłużenie przerwy ma zaktualizować licznik na już otwartej stronie.

    Strona niesie czas końca sprzed przerwy; gdy admin ją przedłuży poleceniem
    extend_countdown, ten czas jest już nieaktualny. Odpowiedź endpointu wraca
    więc do zegara przy każdym odpytaniu.

    Test pilnuje samego okablowania — czy JS w ogóle sięga po tę wartość.
    Zachowania w przeglądarce nie da się tu odtworzyć; chodzi o to, żeby nikt
    nie usunął tej ścieżki niezauważenie.
    """
    content = render_blocked_page()

    assert "status.maintenance_until" in content

"""Testy endpointu statusu odpytywanego w tle przez stronę przerwy technicznej.

Endpoint ma jedno zadanie: pozwolić przeglądarce odróżnić sytuacje, w których
inaczej wyglądałaby tak samo — serwer działa i przerwa trwa, serwer działa
i przerwa się skończyła, serwer nie odpowiada (nginx zwraca 5xx), wreszcie
serwer działa, ale własnego stanu odczytać nie potrafi. Dlatego zawsze
odpowiada kodem 200, a stan niesie w ciele odpowiedzi: kod 503 potrafiłby
wygenerować sam proxy i wtedy pierwsze przypadki byłyby nieodróżnialne od
martwego serwera.

Stąd też ``blocked`` ma trzy wartości, nie dwie. ``null`` znaczy „nie wiem",
a przeglądarka wraca na stronę wyłącznie na jawne ``false``.
"""

import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.db import OperationalError
from django.test import RequestFactory
from django.utils import timezone
from model_bakery import baker

from django_countdown.middleware import (
    DEFAULT_STATUS_PATH,
    CountdownBlockingMiddleware,
    get_poll_interval,
    get_return_url,
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


def render_blocked_page(path="/", raw_path=None, **countdown_kwargs):
    """Wywołaj middleware na zablokowanej stronie i zwróć wyrenderowany HTML.

    ``raw_path`` podstawia ścieżkę już po zbudowaniu requesta. RequestFactory
    normalizuje URL-e tak jak serwer deweloperski, więc bez tego nie da się
    odtworzyć ścieżki, jaką Django dostaje od serwera WSGI, który normalizacji
    nie robi.
    """
    site = Site.objects.get_current()
    fields = {
        "countdown_time": timezone.now() - timedelta(minutes=5),
        "maintenance_until": timezone.now() + timedelta(minutes=20),
    }
    fields.update(countdown_kwargs)
    baker.make(SiteCountdown, site=site, **fields)

    request = RequestFactory().get(path)
    if raw_path is not None:
        request.path = raw_path
    response = CountdownBlockingMiddleware(lambda r: None).process_request(request)
    assert response.status_code == 503
    return response.content.decode("utf-8")


@pytest.mark.django_db
def test_blocked_page_embeds_status_path_and_poll_interval():
    """Strona musi wiedzieć, gdzie i jak często pytać."""
    content = render_blocked_page()

    assert DEFAULT_STATUS_PATH in content
    assert "var pollInterval = 10 * 1000;" in content


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


# ============================================================================
# ADRES POWROTU — nie może wyprowadzić poza witrynę
# ============================================================================


@pytest.mark.django_db
def test_return_url_rejects_a_protocol_relative_path():
    """KRYTYCZNY: ścieżka od "//" to otwarte przekierowanie.

    Przeglądarka czyta ``//evil.example.com/`` jako adres protokołowo-względny,
    więc ``location.replace()`` wyprowadziłoby użytkownika poza witrynę — i to
    po tym, jak zaufał firmowej stronie przerwy technicznej. Serwer
    deweloperski i gunicorn takie ścieżki normalizują, uWSGI nie; pakiet nie
    wie, na czym go uruchomiono.
    """
    content = render_blocked_page(raw_path="//evil.example.com/")

    assert "//evil.example.com" not in content
    assert 'var returnUrl = "/"' in content


def return_url_for(raw_path):
    """Adres powrotu wyliczony dla ścieżki, jaką Django dostało od serwera."""
    request = RequestFactory().get("/")
    request.path = raw_path
    return get_return_url(request)


def test_return_url_neutralises_a_backslash_path():
    """Przeglądarki czytają odwrotny ukośnik w URL-u jak zwykły ukośnik.

    Tu nie ma odrzucenia i nie musi być: ``get_full_path()`` koduje odwrotny
    ukośnik procentowo, a ``%5C`` przeglądarka zostawia w spokoju — adres
    zostaje w obrębie witryny. Test pilnuje właśnie tego, a nie samego napisu:
    gdyby kodowanie kiedyś zniknęło, ścieżka stałaby się protokołowo-względna.
    """
    assert return_url_for("/\\evil.example.com/") == "/%5Cevil.example.com/"


def test_return_url_keeps_the_query_string():
    """Użytkownik ma wrócić do swojego raportu z filtrami, nie do gołej ścieżki."""
    request = RequestFactory().get("/raport/", {"rok": "2026", "typ": "pdf"})

    assert get_return_url(request) == "/raport/?rok=2026&typ=pdf"


@pytest.mark.django_db
def test_blocked_page_guards_the_return_url_in_the_browser_too():
    """Drugie zabezpieczenie tuż przed nawigacją.

    Adres powrotu można podać z własnego widoku, z pominięciem middleware,
    więc ostatnia bramka jest po stronie klienta: cokolwiek nie rozwiązuje się
    do tego samego origin, ląduje na "/".
    """
    content = render_blocked_page()

    assert "window.location.origin" in content


@pytest.mark.django_db
def test_blocked_page_polls_one_request_at_a_time():
    """Karta wracająca na wierzch w trakcie odpytania nie mnoży pętli.

    Bez tej blokady każde przełączenie karty startowało drugi łańcuch
    odpytywania, a każdy łańcuch planuje własnego następcę — tempo rosło
    dwukrotnie na przełączenie, akurat wtedy, gdy serwer jest na tyle wolny,
    że przełączenie trafia w wiszący fetch.

    Test pilnuje obecności blokady; samo zachowanie potwierdzone w przeglądarce
    (trzy cykle ukryj/pokaż przy odpowiedziach opóźnionych o 2,5 s).
    """
    content = render_blocked_page()

    assert "if (inFlight) return;" in content


# ============================================================================
# „NIE WIEM" TO NIE „WOLNE"
# ============================================================================


@pytest.mark.django_db
def test_status_endpoint_reports_unknown_when_the_state_cannot_be_read(mocker):
    """KRYTYCZNY: nierozpoznany stan nie może wyglądać jak odblokowanie.

    Świeży worker z jeszcze niedostępną bazą nie potrafi ustalić, czy witryna
    jest zablokowana. Gdyby zgłosił ``blocked: false``, przeglądarka uznałaby
    to za potwierdzenie i przeniosła użytkownika na stronę, która zaraz
    zwróci 500 — czyli endpoint mówiłby „wchodź" akurat wtedy, gdy nie ma
    pojęcia.
    """
    mocker.patch(
        "django_countdown.middleware.get_current_site",
        side_effect=OperationalError("baza jeszcze nie wstala"),
    )

    response = call_status()

    assert response.status_code == 200
    assert payload(response)["blocked"] is None


@pytest.mark.django_db
def test_middleware_still_fails_open_when_the_state_cannot_be_read(mocker):
    """Zepsuty countdown nigdy nie kładzie działającej witryny.

    Endpoint mówi „nie wiem", ale middleware nadal przepuszcza żądanie —
    to dwie różne odpowiedzi na ten sam brak wiedzy i obie są zamierzone.
    """
    mocker.patch(
        "django_countdown.middleware.get_current_site",
        side_effect=OperationalError("baza jeszcze nie wstala"),
    )
    site = Site.objects.get_current()
    baker.make(
        SiteCountdown, site=site, countdown_time=timezone.now() - timedelta(hours=1)
    )

    request = RequestFactory().get("/")

    assert CountdownBlockingMiddleware(lambda r: None).process_request(request) is None


@pytest.mark.django_db
def test_blocked_page_navigates_only_on_an_explicit_false(mocker):
    """Nawigacja wyłącznie na jawne ``false`` — ``null`` to nie zgoda."""
    content = render_blocked_page()

    assert "status.blocked === false" in content


@pytest.mark.django_db
def test_blocked_page_gives_up_on_a_hung_request():
    """Odpowiedź, która nigdy nie nadchodzi, nie może zatrzymać odpytywania.

    Proxy potrafi przyjąć połączenie i nigdy go nie domknąć. Bez limitu czasu
    ``inFlight`` zostałoby na zawsze ``true`` i karta przestałaby pytać —
    także po powrocie serwera.
    """
    content = render_blocked_page()

    assert "AbortController" in content


# ============================================================================
# APLIKACJA ZAMONTOWANA POD PREFIKSEM (SCRIPT_NAME)
# ============================================================================


@pytest.mark.django_db
def test_status_endpoint_answers_under_a_script_prefix():
    """Aplikacja pod /tenant/ też musi umieć odpowiedzieć na odpytanie."""
    request = RequestFactory(SCRIPT_NAME="/tenant").get(DEFAULT_STATUS_PATH)
    response = CountdownBlockingMiddleware(lambda r: None).process_request(request)

    assert response.status_code == 200
    assert payload(response)["service"] == "django-countdown"


@pytest.mark.django_db
def test_blocked_page_points_the_poll_at_the_mounted_prefix():
    """Przeglądarka pyta pod adresem, który do aplikacji naprawdę trafia."""
    site = Site.objects.get_current()
    baker.make(
        SiteCountdown,
        site=site,
        countdown_time=timezone.now() - timedelta(minutes=5),
        maintenance_until=timezone.now() + timedelta(minutes=20),
    )

    request = RequestFactory(SCRIPT_NAME="/tenant").get("/raport/")
    response = CountdownBlockingMiddleware(lambda r: None).process_request(request)
    content = response.content.decode("utf-8")

    assert 'var statusPath = "/tenant/__countdown_status__/"' in content


# ============================================================================
# WALIDACJA USTAWIEŃ
# ============================================================================


def test_poll_interval_never_goes_negative(settings):
    """Ujemny interwał dałby setTimeout(0) i zapętlone odpytywanie."""
    settings.DJANGO_COUNTDOWN_POLL_INTERVAL = -1

    assert get_poll_interval() == 0


@pytest.mark.django_db
def test_admin_stays_exempt_under_a_script_prefix():
    """KRYTYCZNY: pod prefiksem montowania admin musi zostać otwarty.

    ``request.path`` niesie SCRIPT_NAME, więc ``/tenant/admin/login/`` nie
    zaczyna się od ``/admin/``. Wyjątek przestaje działać dokładnie wtedy,
    gdy jest najbardziej potrzebny: superuser bez aktywnej sesji nie wejdzie
    na stronę logowania, żeby zdjąć blokadę — a obejście blokady wymaga bycia
    zalogowanym.
    """
    site = Site.objects.get_current()
    baker.make(
        SiteCountdown, site=site, countdown_time=timezone.now() - timedelta(hours=1)
    )

    request = RequestFactory(SCRIPT_NAME="/tenant").get("/admin/login/")

    assert CountdownBlockingMiddleware(lambda r: None).process_request(request) is None


@pytest.mark.django_db
def test_static_stays_exempt_under_a_script_prefix():
    """Bez tego strona blokady dostaje samą siebie zamiast arkusza stylów."""
    site = Site.objects.get_current()
    baker.make(
        SiteCountdown, site=site, countdown_time=timezone.now() - timedelta(hours=1)
    )

    request = RequestFactory(SCRIPT_NAME="/tenant").get("/static/style.css")

    assert CountdownBlockingMiddleware(lambda r: None).process_request(request) is None


def test_poll_interval_accepts_a_value_read_from_the_environment(settings):
    """Ustawienia bierze się często z env, a env zwraca napisy."""
    settings.DJANGO_COUNTDOWN_POLL_INTERVAL = "30"

    assert get_poll_interval() == 30


def test_poll_interval_falls_back_when_the_setting_makes_no_sense(settings):
    """KRYTYCZNY: zła wartość nie może położyć strony przerwy.

    ``get_poll_interval()`` jest wołane poza blokiem fail-open middleware'u,
    więc wyjątek stąd oznacza 500 dla każdego odwiedzającego przez całą
    przerwę techniczną — zamiast strony, która tę przerwę tłumaczy.
    """
    settings.DJANGO_COUNTDOWN_POLL_INTERVAL = "co dziesięć sekund"

    assert get_poll_interval() == 10


@pytest.mark.django_db
def test_blocked_page_still_renders_with_a_nonsense_poll_interval(settings):
    """Zasada fail-open obowiązuje też przy błędnej konfiguracji."""
    settings.DJANGO_COUNTDOWN_POLL_INTERVAL = None

    content = render_blocked_page()

    assert "System under maintenance" in content


@pytest.mark.django_db
def test_poll_interval_is_never_localised(settings):
    """KRYTYCZNY: separator tysięcy zamienia liczbę w JS-ie w błąd składni.

    Szablony Django lokalizują liczby. Przy ``USE_THOUSAND_SEPARATOR = True``
    interwał 1800 renderuje się jako ``1,800``, a ``var pollInterval = 1,800
    * 1000;`` to ``SyntaxError`` — który wywala **cały** blok ``<script>``.
    Ginie nie tylko odpytywanie, ale i zegar, i to bez śladu na stronie.
    """
    settings.USE_THOUSAND_SEPARATOR = True
    settings.DJANGO_COUNTDOWN_POLL_INTERVAL = 1800

    content = render_blocked_page()

    assert "var pollInterval = 1800 * 1000;" in content

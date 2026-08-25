import logging

from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import url_has_allowed_host_and_scheme

from .models import SiteCountdown

logger = logging.getLogger(__name__)

DEFAULT_BLOCKED_TEMPLATE = "django_countdown/blocked.html"
DEFAULT_STATUS_PATH = "/__countdown_status__/"
DEFAULT_POLL_INTERVAL = 10

#: Identifies the JSON as ours, so the blocked page can tell a real answer from
#: an error page a reverse proxy invented while the application was down.
SERVICE_MARKER = "django-countdown"

EXEMPT_PREFIXES = ("/admin/", "/static/", "/media/")


def get_blocked_template():
    """Return the template name used to render the blocked page.

    Override via ``DJANGO_COUNTDOWN_BLOCKED_TEMPLATE`` in Django settings, e.g.::

        DJANGO_COUNTDOWN_BLOCKED_TEMPLATE = "django_countdown/blocked_bootstrap.html"
    """
    return getattr(
        settings, "DJANGO_COUNTDOWN_BLOCKED_TEMPLATE", DEFAULT_BLOCKED_TEMPLATE
    )


def get_status_path():
    """Return the path serving the machine-readable maintenance status.

    Override via ``DJANGO_COUNTDOWN_STATUS_PATH`` when the default collides
    with a URL of your own.
    """
    return getattr(settings, "DJANGO_COUNTDOWN_STATUS_PATH", DEFAULT_STATUS_PATH)


def get_poll_interval():
    """Return how many seconds the blocked page waits between status checks.

    Override via ``DJANGO_COUNTDOWN_POLL_INTERVAL``. Zero disables the
    background polling altogether.
    """
    return getattr(settings, "DJANGO_COUNTDOWN_POLL_INTERVAL", DEFAULT_POLL_INTERVAL)


def get_return_url(request):
    """Return where to send the visitor once the site is back.

    Normally the page they asked for. But the browser resolves a path that
    begins with ``//`` — or with a backslash, which it reads as a slash — as
    an address of its own, and would leave the site entirely. Django's
    development server and gunicorn both normalise such paths away before the
    request arrives; uWSGI does not, and a library cannot know which one it is
    running under.
    """
    candidate = request.get_full_path()
    if url_has_allowed_host_and_scheme(candidate, allowed_hosts=None):
        return candidate
    return "/"


def get_blocking_countdown(request):
    """Return the countdown that blocks this request, or ``None`` if it passes.

    This is the single decision both the middleware and the status endpoint
    consult, so the page a browser is shown and the answer it polls for can
    never disagree.
    """
    try:
        current_site = get_current_site(request)
    except Exception:
        logger.exception("countdown middleware: failed to resolve Site")
        return None

    try:
        countdown = SiteCountdown.objects.select_related("site").get(site=current_site)
    except SiteCountdown.DoesNotExist:
        return None

    if not countdown.is_expired():
        return None

    if countdown.is_maintenance_finished():
        return None

    if (
        hasattr(request, "user")
        and request.user.is_authenticated
        and request.user.is_superuser
    ):
        return None

    return countdown


def build_status_response(request):
    """Answer the background poll of a blocked page.

    Always HTTP 200: a reverse proxy with no upstream answers 5xx on its own,
    so the state has to travel in the body to stay distinguishable from it.
    """
    countdown = get_blocking_countdown(request)
    maintenance_until = countdown.maintenance_until if countdown else None

    response = JsonResponse(
        {
            "service": SERVICE_MARKER,
            "blocked": countdown is not None,
            "maintenance_until": (
                maintenance_until.isoformat() if maintenance_until else None
            ),
        }
    )
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


class CountdownBlockingMiddleware(MiddlewareMixin):
    """Block access to the site once the countdown expires.

    Superusers always have access so they can clear the countdown.
    """

    def process_request(self, request):
        if request.path == get_status_path():
            return build_status_response(request)

        if request.path.startswith(EXEMPT_PREFIXES):
            return None

        countdown = get_blocking_countdown(request)
        if countdown is None:
            return None

        return render(
            request,
            get_blocked_template(),
            {
                "countdown": countdown,
                "site": countdown.site,
                "countdown_status_path": get_status_path(),
                "countdown_poll_interval": get_poll_interval(),
                "countdown_return_url": get_return_url(request),
            },
            status=503,
        )

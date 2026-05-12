import logging

from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin

from .models import SiteCountdown

logger = logging.getLogger(__name__)

DEFAULT_BLOCKED_TEMPLATE = "django_countdown/blocked.html"


def get_blocked_template():
    """Return the template name used to render the blocked page.

    Override via ``DJANGO_COUNTDOWN_BLOCKED_TEMPLATE`` in Django settings, e.g.::

        DJANGO_COUNTDOWN_BLOCKED_TEMPLATE = "django_countdown/blocked_bootstrap.html"
    """
    return getattr(
        settings, "DJANGO_COUNTDOWN_BLOCKED_TEMPLATE", DEFAULT_BLOCKED_TEMPLATE
    )


class CountdownBlockingMiddleware(MiddlewareMixin):
    """Block access to the site once the countdown expires.

    Superusers always have access so they can clear the countdown.
    """

    def process_request(self, request):
        if (
            request.path.startswith("/admin/")
            or request.path.startswith("/static/")
            or request.path.startswith("/media/")
        ):
            return None

        try:
            current_site = get_current_site(request)
        except Exception:
            logger.exception("countdown middleware: failed to resolve Site")
            return None

        try:
            countdown = SiteCountdown.objects.get(site=current_site)
        except SiteCountdown.DoesNotExist:
            return None

        if countdown.is_expired():
            if countdown.is_maintenance_finished():
                return None

            if (
                hasattr(request, "user")
                and request.user.is_authenticated
                and request.user.is_superuser
            ):
                return None

            return render(
                request,
                get_blocked_template(),
                {
                    "countdown": countdown,
                    "site": current_site,
                },
                status=503,
            )

        return None

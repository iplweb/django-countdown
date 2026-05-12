import logging

from django.contrib.sites.shortcuts import get_current_site

from .models import SiteCountdown

logger = logging.getLogger(__name__)


def countdown_context(request):
    """Inject the active countdown into the template context.

    Returns the countdown only if it exists and has not yet expired.
    For superusers it also returns the countdown while maintenance is running.
    """
    try:
        current_site = get_current_site(request)
        countdown = SiteCountdown.objects.get(site=current_site)

        if not countdown.is_expired():
            return {"active_countdown": countdown, "maintenance_countdown": None}

        if countdown.is_expired() and not countdown.is_maintenance_finished():
            if (
                hasattr(request, "user")
                and request.user.is_authenticated
                and request.user.is_superuser
            ):
                return {"active_countdown": None, "maintenance_countdown": countdown}
    except SiteCountdown.DoesNotExist:
        pass
    except Exception:
        logger.exception("countdown_context: unexpected error")

    return {"active_countdown": None, "maintenance_countdown": None}

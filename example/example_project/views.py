"""Demo views for the django-countdown example project."""

from datetime import timedelta

from django.contrib.sites.shortcuts import get_current_site
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_safe

from django_countdown.models import SiteCountdown

PREVIEW_TEMPLATES = {
    "plain": ("django_countdown/blocked.html", "Plain (no CSS framework)"),
    "foundation": ("django_countdown/blocked_foundation.html", "Foundation Sites"),
    "bootstrap": ("django_countdown/blocked_bootstrap.html", "Bootstrap 5"),
}


@require_safe
def index(request):
    """Discovery / demo home page for the example project."""
    countdown = SiteCountdown.objects.first()
    return render(
        request,
        "example/index.html",
        {
            "countdown": countdown,
            "preview_variants": PREVIEW_TEMPLATES,
        },
    )


@require_safe
def preview_blocked(request, variant):
    """Render a blocked-page variant with a fake countdown — for preview only."""
    if variant not in PREVIEW_TEMPLATES:
        raise Http404(f"Unknown variant: {variant}")
    template_name, _label = PREVIEW_TEMPLATES[variant]

    fake = SiteCountdown(
        site=get_current_site(request),
        countdown_time=timezone.now() - timedelta(minutes=5),
        maintenance_until=timezone.now() + timedelta(minutes=20),
        message="Preview: planned downtime",
        long_description=(
            "This is a preview of the blocked page. In production this page "
            "is rendered automatically by CountdownBlockingMiddleware when "
            "the configured countdown expires."
        ),
    )
    return render(
        request,
        template_name,
        {"countdown": fake, "site": get_current_site(request)},
    )


@require_safe
def preview_blocked_indefinite(request, variant):
    """Render a blocked-page variant with no maintenance end (indefinite)."""
    if variant not in PREVIEW_TEMPLATES:
        raise Http404(f"Unknown variant: {variant}")
    template_name, _label = PREVIEW_TEMPLATES[variant]

    fake = SiteCountdown(
        site=get_current_site(request),
        countdown_time=timezone.now() - timedelta(minutes=5),
        maintenance_until=None,
        message="Preview: indefinite maintenance",
        long_description=(
            "Indefinite maintenance mode — the site stays blocked until an "
            "admin removes the countdown."
        ),
    )
    return render(
        request,
        template_name,
        {"countdown": fake, "site": get_current_site(request)},
    )


@require_safe
def healthz(request):
    """Tiny no-template endpoint — useful to verify the middleware bypass."""
    return HttpResponse("ok", content_type="text/plain")

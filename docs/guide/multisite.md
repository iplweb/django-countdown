# Multi-site setup

`SiteCountdown` has a `OneToOneField` to
[`Site`](https://docs.djangoproject.com/en/stable/ref/contrib/sites/), which
gives you two things at once: **one countdown per domain**, and per-domain
branding on the maintenance page through `site.name`.

Single-site projects get this for free — set `SITE_ID = 1` and stop reading
after the next section.

## How the current site is resolved

Both the middleware and the context processor call Django's
`get_current_site(request)`, which resolves in this order:

1. If `SITE_ID` is set, return that `Site`.
2. Otherwise, look up a `Site` whose `domain` matches the request's host.
3. If neither works, `Site.DoesNotExist` is raised.

That third case is handled defensively: the failure is logged to the
`django_countdown.middleware` logger and **the request passes through
unblocked**. A countdown that silently does nothing is almost always a
resolution problem — check the log first.

## Per-domain countdowns

Drop `SITE_ID` and let the host decide, which is the usual multi-tenant
arrangement:

```python title="settings.py"
INSTALLED_APPS = [
    # ...
    "django.contrib.sites",
    "django_countdown",
]

# No SITE_ID: get_current_site() matches request.get_host() against
# Site.domain instead.
ALLOWED_HOSTS = ["tenant-a.example.com", "tenant-b.example.com"]
```

Create the `Site` rows once:

```console
$ ./manage.py shell -c "
from django.contrib.sites.models import Site
Site.objects.update_or_create(domain='tenant-a.example.com',
                              defaults={'name': 'Tenant A'})
Site.objects.update_or_create(domain='tenant-b.example.com',
                              defaults={'name': 'Tenant B'})
"
```

Then close one tenant without touching the other:

```console
$ ./manage.py start_countdown --site-id 2 \
      --banner +10m --service +30m \
      --message "Tenant B database migration" --noinput
```

Tenant A stays fully open. Its visitors see no banner, because the context
processor finds no `SiteCountdown` for their site.

!!! warning "`CurrentSiteMiddleware` is not enough"

    `django.contrib.sites.middleware.CurrentSiteMiddleware` sets
    `request.site`, but `get_current_site()` does not read that attribute — it
    re-resolves from `SITE_ID` or the host. Adding it is harmless; relying on
    it to override the resolution is not.

## Closing every site at once

There is no "all sites" mode. Create a row per site — from a loop, if you
have many:

```console
$ ./manage.py shell -c "
from datetime import timedelta
from django.contrib.sites.models import Site
from django.utils import timezone
from django_countdown.models import SiteCountdown

start = timezone.now() + timedelta(minutes=10)
for site in Site.objects.all():
    SiteCountdown.objects.update_or_create(
        site=site,
        defaults={
            'countdown_time': start,
            'maintenance_until': start + timedelta(minutes=30),
            'message': 'Platform-wide maintenance',
        },
    )
"
```

`update_or_create` respects the one-per-site constraint and refreshes any
existing rows. It bypasses `full_clean()`, so validate your timestamps
yourself — the loop above always schedules into the future.

Reopen everything the same way:

```console
$ ./manage.py shell -c "
from django_countdown.models import SiteCountdown
SiteCountdown.objects.all().delete()
"
```

## Branding the maintenance page per tenant

The blocked page renders `site.name` in its `<title>` and footer, so each
tenant gets its own name with no extra work. To go further, branch on the
domain in your own variant:

```django title="templates/django_countdown/blocked.html"
{% extends "django_countdown/blocked_base.html" %}
{% load static %}

{% block blocked_stylesheets %}
  <link rel="stylesheet"
        href="{% static 'css/tenants/'|add:site.domain|add:'.css' %}">
{% endblock %}
```

## Sanity checks

```console
$ ./manage.py shell -c "
from django.contrib.sites.models import Site
from django_countdown.models import SiteCountdown
print('sites:', list(Site.objects.values_list('id', 'domain')))
print('countdowns:', list(SiteCountdown.objects.values_list('site__domain', 'countdown_time')))
"
```

If a countdown exists but nothing is blocked, the mismatch is almost always
between `Site.domain` and the `Host:` header your proxy forwards — including
a stray port, a `www.` prefix, or the default `example.com` row that
`migrate` creates and nobody ever edits.

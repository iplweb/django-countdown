# django-countdown

[![Tests](https://github.com/iplweb/django-countdown/actions/workflows/tests.yml/badge.svg)](https://github.com/iplweb/django-countdown/actions/workflows/tests.yml)
[![Python Version](https://img.shields.io/pypi/pyversions/django-countdown.svg)](https://pypi.org/project/django-countdown/)
[![PyPI Version](https://img.shields.io/pypi/v/django-countdown.svg)](https://pypi.org/project/django-countdown/)
[![License](https://img.shields.io/pypi/l/django-countdown.svg)](LICENSE)

Display a maintenance countdown banner across a Django site, then block public
access (returning HTTP 503) when the countdown expires. Superusers retain
access during maintenance so they can finish the work and clear the countdown.

## Why?

Planned downtime is the worst kind of downtime to communicate badly. Users
land on a half-broken page mid-deploy, hit error logs, file support tickets,
and trust erodes. `django-countdown` lets you announce a maintenance window
*before* it starts (a countdown banner with a real timer), then *during* the
window swap public traffic for an explicit "we're in maintenance" page —
while leaving operators unblocked so they can actually finish the work.

## Features

- **Pre-maintenance banner** — an ultra-visible countdown banner inserted into
  templates via context processor, with a JS timer that ticks live.
- **Hard cutoff at expiry** — middleware returns HTTP 503 and renders a
  branded blocked page once the countdown lapses.
- **Superuser bypass** — admins keep working through the cutoff so they can
  fix the underlying issue and clear the countdown.
- **Maintenance window** — optional `maintenance_until` lets you set a target
  end-time; a second banner appears for superusers and the blocked page shows
  a live countdown to recovery.
- **Per-Site configuration** — uses Django's `sites` framework, so each
  domain in a multi-tenant setup has its own independent countdown.
- **Admin integration** — full Django admin support with status colors and a
  validator preventing past-dated countdowns.

## Supported versions

Authoritative upstream: <https://docs.djangoproject.com/en/dev/faq/install/#what-python-version-can-i-use-with-django>

| Django  | 3.10 | 3.11 | 3.12 | 3.13 | 3.14 | Status                                  |
|---------|------|------|------|------|------|-----------------------------------------|
| 5.2 LTS | ✓    | ✓    | ✓    | ✓    | ✓    | Active LTS (extended support Apr 2028)  |
| 6.0     | —    | —    | ✓    | ✓    | ✓    | Mainstream Aug 2026, extended Apr 2027  |

8 cells in total are exercised by the CI matrix on every push.

## Installation

### Using uv (recommended)

```bash
uv add django-countdown
```

### Using pip

```bash
pip install django-countdown
```

### Project configuration

Add to `INSTALLED_APPS` — the `django.contrib.sites` framework must also be
installed:

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.sites",
    "django_countdown",
]

SITE_ID = 1
```

Add the blocking middleware **after** Django's auth middleware (it needs
`request.user`):

```python
MIDDLEWARE = [
    # ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_countdown.middleware.CountdownBlockingMiddleware",
]
```

Add the context processor so the banner partials see the active countdown:

```python
TEMPLATES = [
    {
        # ...
        "OPTIONS": {
            "context_processors": [
                # ...
                "django_countdown.context_processors.countdown_context",
            ],
        },
    },
]
```

Run migrations:

```bash
./manage.py migrate
```

## Quick start

Create a `SiteCountdown` row (one per `django.contrib.sites.Site`) via the
Django admin, providing:

- `countdown_time` — when access starts being blocked.
- `maintenance_until` (optional) — when public access resumes.
- `message` — short banner headline (max 200 chars).
- `long_description` (optional) — extended copy shown on the blocked page.

The package exposes two template partials you can `{% include %}` from your
own base layout:

```django
{% include "django_countdown/countdown_banner.html" %}
```

Renders a banner before the countdown expires; switches to a subdued
"maintenance in progress" banner for superusers after expiry until
`maintenance_until` passes. Two context variables are populated by the
context processor: `active_countdown` (pre-maintenance) and
`maintenance_countdown` (during maintenance, superusers only).

The middleware automatically serves `django_countdown/blocked.html` for
non-superuser requests once the countdown has expired and maintenance is
ongoing.

A working end-to-end example lives under [`example/`](./example/) — start
there if you want to see the package wired up in a minimal Django project.

## Blocked-page variants

Three blocked-page templates ship with the package; pick one via
`DJANGO_COUNTDOWN_BLOCKED_TEMPLATE` in your settings:

| Template                                       | Requirements                            |
|------------------------------------------------|-----------------------------------------|
| `django_countdown/blocked.html` *(default)*    | None — ships its own CSS                |
| `django_countdown/blocked_foundation.html`     | Foundation Sites + foundation-icons CSS |
| `django_countdown/blocked_bootstrap.html`      | Bootstrap 5 (loaded from CDN)           |

```python
# settings.py
DJANGO_COUNTDOWN_BLOCKED_TEMPLATE = "django_countdown/blocked_bootstrap.html"
```

All three inherit from `django_countdown/blocked_base.html`, which exposes a
`{% block blocked_stylesheets %}` you can override in your own subclass if
you need a different framework.

`countdown_banner.html` ships its own stylesheet via `{% static %}` and has
**no external Python dependencies** beyond Django itself (no
`django-compressor`, no `django-sass-processor`).

## Configuration

The package does not require any project-level Django settings. The middleware
exempts `/admin/`, `/static/`, and `/media/` URL prefixes from blocking by
default.

## Development

```bash
git clone https://github.com/iplweb/django-countdown.git
cd django-countdown
uv sync --all-extras
uv run pytest
```

## License

MIT — see [LICENSE](LICENSE) for details.

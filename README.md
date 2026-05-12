# django-countdown

Display a maintenance countdown banner across a Django site, then block public
access (returning HTTP 503) when the countdown expires. Superusers retain
access during maintenance so they can finish the work and clear the countdown.

## Installation

```bash
pip install django-countdown
```

Add to your Django project's `INSTALLED_APPS` (the `django.contrib.sites`
framework must also be installed):

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

## Usage

Create a `SiteCountdown` row (one per `django.contrib.sites.Site`) via the
Django admin, providing:

- `countdown_time` — when access starts being blocked.
- `maintenance_until` (optional) — when public access resumes again.
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

## Requirements

- Python ≥ 3.10
- Django ≥ 5.2
- `django.contrib.sites` enabled (`SITE_ID` set)

### Optional / template-level requirements

`countdown_banner.html` uses `{% load compress %}` (from
[django-compressor](https://django-compressor.readthedocs.io/)) to bundle its
CSS. If you include the banner partial in your templates, install
`django-compressor` and add it to `INSTALLED_APPS`, or fork the template and
drop the `{% compress %}` wrapping.

`blocked.html` references Foundation CSS and Foundation-Icons via
`{% static %}`. If you serve those files from your project's static pipeline
they will resolve; otherwise the blocked page will degrade visually but still
render the maintenance message.

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

MIT — see [LICENSE](./LICENSE).

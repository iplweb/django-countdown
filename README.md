# django-countdown

[![Tests](https://github.com/iplweb/django-countdown/actions/workflows/tests.yml/badge.svg)](https://github.com/iplweb/django-countdown/actions/workflows/tests.yml)
[![Docs](https://github.com/iplweb/django-countdown/actions/workflows/docs.yml/badge.svg)](https://iplweb.github.io/django-countdown/)
[![Python Version](https://img.shields.io/pypi/pyversions/django-countdown.svg)](https://pypi.org/project/django-countdown/)
[![PyPI Version](https://img.shields.io/pypi/v/django-countdown.svg)](https://pypi.org/project/django-countdown/)
[![License](https://img.shields.io/pypi/l/django-countdown.svg)](LICENSE)

Display a maintenance countdown banner across a Django site, then block public
access (returning HTTP 503) when the countdown expires. Superusers retain
access during maintenance so they can finish the work and clear the countdown.

**📖 Full documentation: <https://iplweb.github.io/django-countdown/>**

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
- **A command per verb** — `start_countdown` schedules a window,
  `show_countdown` reports where it stands (with `--json` for monitoring),
  `extend_countdown` and `shorten_countdown` move its boundaries when the plan
  slips, and `stop_countdown` reopens the site.
- **Dead man's switch** — `extend_countdown --at-least 5m` raises a floor
  rather than adding time, so a deploy loop can hold the site closed while it
  works and let it reopen by itself if the deploy dies.
- **Admin integration** — full Django admin support alongside the commands.

## Supported versions

| Django  | 3.10 | 3.11 | 3.12 | 3.13 | 3.14 | Status                                  |
|---------|------|------|------|------|------|-----------------------------------------|
| 5.2 LTS | ✓    | ✓    | ✓    | ✓    | ✓    | Active LTS (extended support Apr 2028)  |
| 6.0     | —    | —    | ✓    | ✓    | ✓    | Mainstream Aug 2026, extended Apr 2027  |

All 8 cells are exercised by the CI matrix on every push. Django is the only
runtime dependency.

## Installation

```bash
uv add django-countdown      # or: pip install django-countdown
```

Add the app, the middleware and the context processor to your settings:

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.sites",
    "django_countdown",
]
SITE_ID = 1

MIDDLEWARE = [
    # ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_countdown.middleware.CountdownBlockingMiddleware",
]

TEMPLATES = [{
    # ...
    "OPTIONS": {"context_processors": [
        # ...
        "django_countdown.context_processors.countdown_context",
    ]},
}]
```

Then `./manage.py migrate`, and include the banner in your base template:

```django
{% include "django_countdown/countdown_banner.html" %}
```

Full walkthrough:
[Installation](https://iplweb.github.io/django-countdown/getting-started/installation/).

## Quick start

```bash
./manage.py start_countdown --banner +15m --service +30m \
    --message "Database upgrade" --noinput
```

Banner shows for 15 minutes, then the site returns 503 for 30 minutes, then
reopens by itself. Check on it with `./manage.py show_countdown`, and reopen
early with `./manage.py stop_countdown`. Use `--service indefinite` to stay
closed until you do. See
[Quickstart](https://iplweb.github.io/django-countdown/getting-started/quickstart/).

A working end-to-end example lives under [`example/`](./example/).

## Documentation

| | |
|---|---|
| [How it works](https://iplweb.github.io/django-countdown/guide/how-it-works/) | The state machine, who sees what, failure behaviour |
| [Countdown banner](https://iplweb.github.io/django-countdown/guide/banner/) | Including, styling and overriding the banner |
| [Blocked page](https://iplweb.github.io/django-countdown/guide/blocked-page/) | Three shipped variants and how to write your own |
| [Scheduling a countdown](https://iplweb.github.io/django-countdown/guide/management-command/) | Every option of `start_countdown` |
| [Managing a running countdown](https://iplweb.github.io/django-countdown/guide/managing-a-countdown/) | `show`, `stop`, `extend`, `shorten`, and the deploy patterns |
| [Multi-site setup](https://iplweb.github.io/django-countdown/guide/multisite/) | One countdown per domain |
| [Reference](https://iplweb.github.io/django-countdown/reference/settings/) | Settings, model, template context, template blocks |

## Development

```bash
git clone https://github.com/iplweb/django-countdown.git
cd django-countdown
uv sync --all-extras
uv run pytest
```

See
[Contributing](https://iplweb.github.io/django-countdown/contributing/).

## License

MIT — see [LICENSE](LICENSE) for details.

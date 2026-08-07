# django-countdown

Announce planned Django downtime **before** it starts, then close the site
cleanly **while** it happens — without locking yourself out.

`django-countdown` gives you two things that work together:

1. A **countdown banner** injected into your own templates, with a live JS
   timer counting down to the moment the site closes.
2. A **blocking middleware** that returns `HTTP 503` and renders a branded
   maintenance page once that moment arrives — except for superusers, who
   keep browsing so they can finish the work.

Everything is driven by a single database row per
[`Site`](https://docs.djangoproject.com/en/stable/ref/contrib/sites/), which
you create from the Django admin or with one command:

```console
$ ./manage.py start_countdown --banner +15m --service +30m \
      --message "Database upgrade" --noinput
✓ Created countdown for example.com.
```

There is a command for every other verb too — because the moment you need them,
the site is usually already closed and the plan is already slipping:

```console
$ ./manage.py show_countdown       # which phase, and how long left?
$ ./manage.py extend_countdown     # it is taking longer than planned
$ ./manage.py shorten_countdown    # it is going faster
$ ./manage.py stop_countdown       # done — reopen the site
```

## Why it exists

Planned downtime is the worst kind of downtime to communicate badly. Users
land on a half-broken page mid-deploy, hit error logs, file support tickets,
and trust erodes. Announcing the window in advance and serving an honest 503
during it turns an incident into a non-event.

## Features

<div class="grid cards" markdown>

- :material-bullhorn: **Pre-maintenance banner**

    An ultra-visible banner with a timer that ticks live, injected through a
    context processor and included wherever you want it.

- :material-lock-clock: **Hard cutoff at expiry**

    Middleware returns `HTTP 503` and renders a maintenance page the moment
    the countdown lapses — a status code that proxies and crawlers understand.

- :material-shield-account: **Superuser bypass**

    Admins keep working through the cutoff so they can finish the job and
    clear the countdown.

- :material-timer-sand: **Bounded or indefinite windows**

    Set `maintenance_until` for auto-recovery, or leave it empty to stay
    blocked until someone explicitly unblocks.

- :material-server-network: **Per-Site configuration**

    One countdown per domain via `django.contrib.sites` — multi-tenant
    projects close one site without touching the rest.

- :material-translate: **Translatable**

    Every user-visible string goes through `gettext`; English and Polish
    catalogs ship with the package.

</div>

## Where to go next

| I want to… | Read |
|---|---|
| Install and wire it into settings | [Installation](getting-started/installation.md) |
| See a countdown running in three minutes | [Quickstart](getting-started/quickstart.md) |
| Understand who sees what, and when | [How it works](guide/how-it-works.md) |
| Restyle the maintenance page | [Blocked page](guide/blocked-page.md) |
| Script downtime from CI or a deploy hook | [Scheduling a countdown](guide/management-command.md) |
| Check on, adjust or end a window already running | [Managing a running countdown](guide/managing-a-countdown.md) |
| Look up a field, setting or template block | [Reference](reference/settings.md) |

## Requirements

| Django | 3.10 | 3.11 | 3.12 | 3.13 | 3.14 |
|---------|------|------|------|------|------|
| 5.2 LTS | ✓ | ✓ | ✓ | ✓ | ✓ |
| 6.0 | — | — | ✓ | ✓ | ✓ |
| 6.1 | — | — | ✓ | ✓ | ✓ |

All eleven cells run in CI on every push. The only runtime dependency is
Django itself.

## Licence

MIT — see [LICENSE](https://github.com/iplweb/django-countdown/blob/main/LICENSE).

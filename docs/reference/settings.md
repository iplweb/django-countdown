# Settings

The package needs no project settings to function. Three are available.

## `DJANGO_COUNTDOWN_BLOCKED_TEMPLATE`

Template rendered by `CountdownBlockingMiddleware` when a request is blocked.

| | |
|---|---|
| **Type** | `str` — a template name |
| **Default** | `"django_countdown/blocked.html"` |
| **Read** | On every blocked request, via `getattr(settings, ...)` |

```python title="settings.py"
DJANGO_COUNTDOWN_BLOCKED_TEMPLATE = "django_countdown/blocked_bootstrap.html"
```

Shipped values:

- `django_countdown/blocked.html` — self-contained, no framework
- `django_countdown/blocked_bootstrap.html` — Bootstrap 5 from jsDelivr
- `django_countdown/blocked_foundation.html` — Foundation Sites from your own
  static files

Any template name resolvable by your loaders works, including one of your
own. It is rendered with the countdown, the site and the polling parameters —
see [Template context](context.md#blocked-page-context) — and returned with
`status=503`.

!!! note "Read at request time, not at import time"

    The setting is looked up on each blocked request, so
    `@override_settings(DJANGO_COUNTDOWN_BLOCKED_TEMPLATE=...)` works in tests
    without reloading the middleware.

    An invalid template name is not validated at startup — it raises
    `TemplateDoesNotExist` on the first blocked request, i.e. exactly when
    your site is already down. Verify the value before you rely on it.

## `DJANGO_COUNTDOWN_STATUS_PATH`

Path at which the middleware answers the background poll that the blocked
page runs — see [Waiting for the site to come back](../guide/blocked-page.md#waiting-for-the-site-to-come-back).

| | |
|---|---|
| **Type** | `str` — an absolute path, matched exactly |
| **Default** | `"/__countdown_status__/"` |
| **Read** | On every request, via `getattr(settings, ...)` |

```python title="settings.py"
DJANGO_COUNTDOWN_STATUS_PATH = "/_internal/countdown-status/"
```

The middleware compares `request.path_info` to this value **before**
anything else, so the endpoint needs no entry in your `URLconf` and answers
even while the rest of the site is blocked. `path_info` rather than `path`,
so an application mounted under a prefix still matches; the blocked page is
handed the prefixed URL to ask for. Change it only if the default collides with
a URL of your own; the leading and trailing slashes are part of the match.

Whatever you set here is exempt from blocking, so treat it as a public
endpoint. It discloses exactly two facts: whether the site is currently
blocked, and when the maintenance window is scheduled to end — the same two
facts the maintenance page shows to anyone who visits.

## `DJANGO_COUNTDOWN_POLL_INTERVAL`

Seconds the blocked page waits between those background checks.

| | |
|---|---|
| **Type** | `int` — seconds |
| **Default** | `10` |
| **Read** | On every blocked request, via `getattr(settings, ...)` |

```python title="settings.py"
DJANGO_COUNTDOWN_POLL_INTERVAL = 30
```

Each check is scheduled at the interval ±20 % of jitter. The jitter is not
cosmetic: when a window ends, every waiting tab wakes up at once against a
server that has just started, and spreading those requests is the difference
between a warm-up and a stampede.

`0` disables the polling entirely — no status line, no `fetch`, and the
page then has no way to notice that the site is back. Negative values are
floored to `0`: a negative delay is one the browser runs immediately, which
would turn every waiting tab into a request loop.

A string is accepted and converted, since settings are often read from the
environment. A value that is not a number at all logs a warning and falls
back to the default rather than raising — this is read while rendering the
blocked page, and an exception there would answer every visitor with a 500
for the length of the window, in place of the page explaining it.

## Django settings that matter

These are Django's own, but the package will not behave without them.

| Setting | Why |
|---|---|
| `INSTALLED_APPS` ∋ `django.contrib.sites` | `SiteCountdown.site` points at `Site` |
| `INSTALLED_APPS` ∋ `django_countdown` | Models, templates, translations, the management command |
| `SITE_ID` | How `get_current_site()` resolves — unless you match by host, see [Multi-site setup](../guide/multisite.md) |
| `MIDDLEWARE` order | `CountdownBlockingMiddleware` must come **after** `AuthenticationMiddleware`, or superusers get blocked |
| `TEMPLATES` → `context_processors` | `countdown_context` is required for the banner |
| `STATIC_URL` / staticfiles | The default maintenance page and the banner load their CSS with `{% static %}` |
| `USE_TZ` | Timestamps are compared with `timezone.now()`; `USE_TZ = True` is strongly recommended |

## Exempt URL prefixes

Three prefixes are never blocked:

```python
"/admin/"    # so you can always unblock the site
"/static/"   # so the maintenance page can style itself
"/media/"    # so referenced uploads still resolve
```

The status path above is exempt too, but it is not one of these: it is
matched exactly rather than as a prefix, it is configurable, and it is
handled before them.

All of them are matched against the path as your `URLconf` sees it, without
the mount prefix — an application served under `/tenant` keeps its admin
reachable during a window.

!!! warning "Hardcoded, not configurable"

    They are literals in `CountdownBlockingMiddleware.process_request`, and no
    setting overrides them. Two consequences:

    - **If you moved the admin** to, say, `/manage/`, that path *is* blocked
      for non-superusers. Superusers still get through — the bypass is
      independent — so you can still unblock, but staff cannot reach the admin
      during a window.
    - **If you serve static or media from another prefix** (`/assets/`,
      `/cdn/`), those requests are blocked and the maintenance page renders
      unstyled. Serving them from a separate domain or a CDN sidesteps the
      problem entirely, since the middleware never sees those requests.

    Health checks are *not* exempt. A probe at `/healthz/` starts returning
    503 during a window — which may be exactly what you want behind a load
    balancer, or may take your instance out of rotation. Decide deliberately.

    If you need different prefixes today, subclass the middleware:

    ```python title="yourapp/middleware.py"
    from django_countdown.middleware import CountdownBlockingMiddleware

    EXEMPT = ("/manage/", "/assets/", "/healthz/")


    class CustomCountdownMiddleware(CountdownBlockingMiddleware):
        def process_request(self, request):
            if request.path.startswith(EXEMPT):
                return None
            return super().process_request(request)
    ```

    Register your subclass in `MIDDLEWARE` instead of the original. Calling
    `super()` keeps the status endpoint working; returning early for a prefix
    that happens to contain it would take it out.

## Logging

Two loggers, both named after their module, both used only for unexpected
failures:

| Logger | Emits |
|---|---|
| `django_countdown.middleware` | `logger.exception` when the current `Site` cannot be resolved |
| `django_countdown.context_processors` | `logger.exception` on any unexpected error while building the context |

Both paths fail open — the request continues unblocked. Route these loggers
somewhere you will actually read; a countdown that quietly does nothing
usually announced itself here first.

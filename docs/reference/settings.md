# Settings

The package needs no project settings to function. Exactly one is available.

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
own. It is rendered with `{"countdown": ..., "site": ...}` — see
[Template context](context.md#blocked-page-context) — and returned with
`status=503`.

!!! note "Read at request time, not at import time"

    The setting is looked up on each blocked request, so
    `@override_settings(DJANGO_COUNTDOWN_BLOCKED_TEMPLATE=...)` works in tests
    without reloading the middleware.

    An invalid template name is not validated at startup — it raises
    `TemplateDoesNotExist` on the first blocked request, i.e. exactly when
    your site is already down. Verify the value before you rely on it.

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

    Register your subclass in `MIDDLEWARE` instead of the original.

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

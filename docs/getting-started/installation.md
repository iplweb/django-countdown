# Installation

## Install the package

=== "uv"

    ```console
    $ uv add django-countdown
    ```

=== "pip"

    ```console
    $ pip install django-countdown
    ```

The only runtime dependency is Django (5.2 or newer). No asset pipeline, no
`django-compressor`, no `django-sass-processor` — the shipped CSS is plain
`.css` served through `{% static %}`.

## Configure the project

Three settings edits and one migration. All of them are required; the package
does nothing until the middleware and the context processor are registered.

### 1. Installed apps

`django_countdown` stores one countdown per
[`Site`](https://docs.djangoproject.com/en/stable/ref/contrib/sites/), so
`django.contrib.sites` must be installed too:

```python title="settings.py" hl_lines="3 5 8"
INSTALLED_APPS = [
    # ...
    "django.contrib.sites",
    "django.contrib.staticfiles",
    "django_countdown",
]

SITE_ID = 1
```

!!! warning "`SITE_ID` or a host-matching Site row"

    The middleware resolves the current site with `get_current_site()`. That
    needs either `SITE_ID` set, or a `Site` row whose `domain` matches the
    request's host. Without one, resolution fails, the failure is logged, and
    the request is allowed through unblocked. See
    [Multi-site setup](../guide/multisite.md).

### 2. Middleware

Add the blocking middleware **after** Django's `AuthenticationMiddleware` —
it reads `request.user` to decide whether to let a superuser through:

```python title="settings.py" hl_lines="5"
MIDDLEWARE = [
    # ...
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_countdown.middleware.CountdownBlockingMiddleware",
]
```

!!! danger "Order matters"

    Placed *before* `AuthenticationMiddleware`, `request.user` does not exist
    yet. The middleware degrades safely — it treats the request as anonymous —
    which means **superusers get blocked out of their own site**.

### 3. Context processor

The banner partial reads its data from the template context, so register the
processor:

```python title="settings.py" hl_lines="9"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # ...
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django_countdown.context_processors.countdown_context",
            ],
        },
    },
]
```

You only need this if you intend to show the pre-maintenance banner. The
blocked page itself is rendered by the middleware and does not depend on the
context processor.

### 4. Migrate

```console
$ ./manage.py migrate
```

This creates the `django_countdown_sitecountdown` table (and the `django_site`
table, if `sites` is new to your project).

### 5. Include the banner

Add one line to your base layout, typically right after `<body>`:

```django title="templates/base.html"
{% include "django_countdown/countdown_banner.html" %}
```

The partial renders nothing at all when no countdown is active, so it is safe
to leave in place permanently.

## Verify the installation

```console
$ ./manage.py check
System check identified no issues (0 silenced).

$ ./manage.py start_countdown --banner +2m --service +5m \
      --message "Installation smoke test" --noinput
✓ Created countdown for example.com.
```

Reload any page: the banner should appear. Two minutes later, log out (or use
a private window) and reload again — you should get the maintenance page with
status 503, while your superuser session keeps working.

To clean up, delete the row in the admin under **Site shutdown countdowns**.

## Optional settings

The package needs no project settings to work. One is available for choosing
a different maintenance-page design — see [Settings](../reference/settings.md).

## A working example

The repository ships a complete minimal project under
[`example/`](https://github.com/iplweb/django-countdown/tree/main/example) with
the middleware, context processor, sites framework and translations already
wired up, plus preview URLs for every blocked-page variant.

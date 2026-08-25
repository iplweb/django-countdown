# Example project for `django-countdown`

Minimal Django project demonstrating how to wire up `django-countdown`:

- The countdown blocking middleware sits after `AuthenticationMiddleware`.
- The countdown context processor is registered in `TEMPLATES`.
- `django.contrib.sites` is installed (required by the package).
- `django.middleware.locale.LocaleMiddleware` is enabled so the package
  picks up the user's `Accept-Language` (English source / Polish translation
  ship out of the box).

## Run it

From the repository root:

```bash
uv sync --all-extras
cd example
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Then visit:

- <http://127.0.0.1:8000/> — discovery page that previews each blocked-page
  variant and links into the admin.
- <http://127.0.0.1:8000/admin/> — manage countdowns. Superusers are never
  blocked, so this stays reachable even after expiry.
- <http://127.0.0.1:8000/healthz/> — simple endpoint that gets blocked once
  the countdown expires (HTTP 503).

## Start a countdown

Interactive:

```bash
uv run python manage.py start_countdown
```

Non-interactive — service mode lasts 30 minutes:

```bash
uv run python manage.py start_countdown \
    --banner +5m --service +30m --message "Database upgrade" --noinput
```

Non-interactive — site is locked **indefinitely** (no auto-unblock):

```bash
uv run python manage.py start_countdown \
    --banner +1m --service indefinite --noinput
```

To remove an indefinite block: delete the row from the admin
(`Site shutdown countdowns`) or via `manage.py shell`.

## Try a different blocked-page theme

Three CSS-framework-agnostic variants ship in the package:

| Setting value | Look |
| --- | --- |
| `django_countdown/blocked.html` (default) | Plain, self-contained |
| `django_countdown/blocked_foundation.html` | Foundation Sites |
| `django_countdown/blocked_bootstrap.html` | Bootstrap 5 (via CDN) |

Set `DJANGO_COUNTDOWN_BLOCKED_TEMPLATE` in `example_project/settings.py`
to pick one site-wide, or preview each at
`/preview/{plain|foundation|bootstrap}/` and
`/preview/{...}/indefinite/`.

The preview URLs render with polling switched off — they are static shots of
the page. The real thing navigates away as soon as the site is back, which on
a preview would bounce you off after a few seconds.

## Watch the page bring itself back

With a countdown running, open <http://127.0.0.1:8000/healthz/>. You get the
maintenance page and a status line that says it is checking on the server.
Leave it open and:

```bash
# Stop the server (Ctrl-C). Within a few seconds the line changes to
# "The server is restarting - please wait...", and the page stays put.

# Start it again, then clear the countdown from another shell:
uv run python manage.py stop_countdown
```

The page notices on its own and takes you to `/healthz/`, the URL you asked
for in the first place. Poll it directly to see what it is reading:

```bash
curl -s http://127.0.0.1:8000/__countdown_status__/
```

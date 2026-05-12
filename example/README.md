# Example project for `django-countdown`

Minimal Django project demonstrating how to wire up `django-countdown`:

- The countdown blocking middleware sits after `AuthenticationMiddleware`.
- The countdown context processor is registered in `TEMPLATES`.
- `django.contrib.sites` is installed (required by the package).

## Run it

From the repository root:

```bash
uv sync --all-extras
cd example
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Then visit http://127.0.0.1:8000/admin/ → "Odliczania do zamknięcia
serwisu" → add one. Set `countdown_time` ~1 minute in the future; after that,
any non-admin request to `/` returns HTTP 503 with the blocked page. Set
`maintenance_until` further into the future to keep superusers visible to the
maintenance banner.

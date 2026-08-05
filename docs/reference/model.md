# `SiteCountdown`

```python
from django_countdown.models import SiteCountdown
```

One row per `Site`, holding the whole state of a maintenance window.

- **Table** — `django_countdown_sitecountdown`
- **Verbose name** — *Site shutdown countdown* / *Site shutdown countdowns*
- **Ordering** — `["-countdown_time"]`, newest window first

## Fields

| Field | Type | Null | Description |
|---|---|---|---|
| `site` | `OneToOneField(Site, on_delete=CASCADE)` | no | The domain this countdown closes. One-to-one, so a site has at most one countdown; deleting the site deletes the countdown. |
| `countdown_time` | `DateTimeField` | yes | When the site starts returning 503. `NULL` disables blocking entirely — the row exists but never matches. |
| `maintenance_until` | `DateTimeField` | yes | When the site reopens. `NULL` means indefinite: it stays blocked until the row is deleted. |
| `message` | `CharField(max_length=200)` | no | Headline shown in the banner and on the maintenance page. |
| `long_description` | `TextField(blank=True, default="")` | no | Optional longer text, shown on the maintenance page only, rendered through `linebreaks`. |
| `created_at` | `DateTimeField(auto_now_add=True)` | no | Set on creation. |
| `updated_at` | `DateTimeField(auto_now=True)` | no | Refreshed on every `save()`. |

!!! warning "`countdown_time = NULL` never blocks, but does render a banner"

    `is_expired()` returns `False` for a row with no countdown time, so the
    middleware never blocks — but the context processor still publishes it as
    `active_countdown`, and the banner renders with an **empty timer** (there
    is no target time to count down to).

    A row like this is reachable from the admin, where `Countdown time` is an
    optional field. Treat it as unfinished configuration, not as a way to
    park a countdown: delete the row instead.

## Methods

### `is_expired() -> bool`

`True` once `now >= countdown_time`, i.e. the window has opened. Always
`False` when `countdown_time` is `NULL`.

Exposed in the admin as the boolean column **Expired?**.

### `is_indefinite() -> bool`

`True` when a countdown is set but has no end — `countdown_time is not None
and maintenance_until is None`. Admin column **Indefinite?**.

### `is_maintenance_finished() -> bool`

`True` once `now >= maintenance_until`. **Always `False` for indefinite
maintenance**, which is what keeps an open-ended window open.

This is the method that reopens the site: the middleware stops blocking as
soon as it returns `True`.

### `time_remaining() -> str`

Human-readable time until `countdown_time`, translated:

| State | Returns |
|---|---|
| `countdown_time is None` | `"Not set"` |
| `is_expired()` | `"Expired"` |
| otherwise | e.g. `"2 days 3 h 15 min"` |

Components that are zero are dropped, except that seconds are always shown
when nothing else would be. This is a snapshot rendered server-side — it does
not tick. For a live timer, use the banner's JavaScript.

### `maintenance_time_remaining() -> int | None`

Whole seconds until `maintenance_until`. `None` when maintenance is
indefinite **or already finished** — those two cases are not distinguishable
from the return value alone; check `is_indefinite()` if you need to tell them
apart.

### `maintenance_duration_minutes() -> int | None`

Planned window length in minutes, `maintenance_until - countdown_time`.
`None` if either timestamp is missing. The banner uses it for "Estimated
maintenance duration: 30 minutes".

Note this is the *planned* duration, computed from the two timestamps — it
does not shrink as the window elapses.

### `clean()`

Model validation, run by `full_clean()` and therefore by the admin and by
`start_countdown`, but **not** by plain `save()`, `update()`,
`update_or_create()` or `bulk_create()`.

| Rule | Field error raised on |
|---|---|
| `countdown_time` must be in the future | `countdown_time` |
| `maintenance_until` must be later than `countdown_time` | `maintenance_until` |

!!! danger "The first rule applies to every save, forever"

    Once `countdown_time` is in the past, the row can no longer be saved
    through validated paths — the admin form rejects it even if you only
    touched `maintenance_until`. Delete and recreate, or use
    `QuerySet.update()` to bypass validation. See
    [Django admin](../guide/admin.md#validation-rules).

### `__str__()`

`"{site.domain} - {message} ({countdown_time})"`.

## Working with it in code

Creating a window programmatically, with validation:

```python
from datetime import timedelta

from django.contrib.sites.models import Site
from django.utils import timezone

from django_countdown.models import SiteCountdown

start = timezone.now() + timedelta(minutes=15)

countdown = SiteCountdown(
    site=Site.objects.get_current(),
    countdown_time=start,
    maintenance_until=start + timedelta(minutes=30),
    message="Database upgrade",
)
countdown.full_clean()   # enforce clean(); skip only if you know why
countdown.save()
```

Replacing whatever is there (the pattern `start_countdown` uses):

```python
SiteCountdown.objects.update_or_create(
    site=site,
    defaults={
        "countdown_time": start,
        "maintenance_until": None,     # indefinite
        "message": "Unplanned maintenance",
    },
)
```

Reopening:

```python
SiteCountdown.objects.filter(site=site).delete()
```

Checking state without a request:

```python
countdown = SiteCountdown.objects.filter(site=site).first()
if countdown and countdown.is_expired() and not countdown.is_maintenance_finished():
    ...  # the site is currently closed to the public
```

That condition is exactly what the middleware evaluates, minus the superuser
bypass — see [How it works](../guide/how-it-works.md#request-lifecycle).

## Migrations

Five migrations ship with the package, `0001_initial` through
`0005_alter_sitecountdown_options_and_more`. They are ordinary Django
migrations; `./manage.py migrate` applies them, and the app declares a
dependency on `sites`.

# Django admin

The admin is where you schedule downtime by hand, and — more importantly —
the way back in when the site is closed. `/admin/` is exempt from blocking,
so a countdown can never lock you out of the tool that removes it.

Look for **Site shutdown countdown → Site shutdown countdowns**.

## Change list

| Column | Notes |
|---|---|
| Site | The domain this countdown closes |
| Message | Banner headline |
| Countdown time | When the site closes |
| Maintenance end | When it reopens; empty means indefinite |
| Expired? | Boolean icon — has the window opened |
| Indefinite? | Boolean icon — scheduled with no end |
| Time remaining | Text: `Not set`, `Expired`, or e.g. `1 h 12 min 30 sec` |
| Created at | Row creation timestamp |

Filters are available on **Site** and **Countdown time**; search covers
**Message** and **Long description**.

!!! info "The list is a snapshot"

    Every computed column is evaluated when the page renders. Nothing ticks
    — reload to refresh the remaining time.

## Add / change form

The form is grouped into three fieldsets:

**Basic information** — `Site`, `Countdown time`, `Maintenance end`. Leaving
the maintenance end empty keeps the site blocked indefinitely once the
countdown expires.

**Messages** — `Short message` (max 200 characters, appears in the banner and
on the maintenance page) and `Long description` (optional paragraph, shown on
the maintenance page only, with line breaks preserved).

**Metadata** — collapsed by default: `Created at`, `Updated at` and the
read-only `Time remaining`.

## Validation rules

`SiteCountdown.clean()` enforces two invariants, and the admin surfaces both
as field errors:

| Rule | Message |
|---|---|
| `countdown_time` must be in the future | *Countdown time cannot be in the past. Pick a future date.* |
| `maintenance_until` must be later than `countdown_time` | *Maintenance end must be later than the countdown time.* |

!!! danger "You cannot edit a countdown once it has expired"

    The first rule is checked on every save, not only on creation. As soon as
    `countdown_time` is in the past, **any** save of that row fails — including
    one that only extends `maintenance_until` to buy yourself more time.

    Workarounds, in order of preference:

    1. **Delete the row and create a new one** with a fresh, near-future
       countdown time. This is the intended path.
    2. **Schedule indefinitely from the start** when the work has uncertain
       length, and delete the row when you are done — no extension needed.
    3. **Update in the shell**, which bypasses `full_clean()`:

        ```console
        $ ./manage.py shell -c "
        from datetime import timedelta
        from django.utils import timezone
        from django_countdown.models import SiteCountdown
        SiteCountdown.objects.filter(site_id=1).update(
            maintenance_until=timezone.now() + timedelta(minutes=30)
        )
        "
        ```

        `QuerySet.update()` writes straight to the database without running
        model validation. Use it deliberately, and only for pushing an end
        time out.

    One field remains freely editable while blocked: nothing stops you from
    deleting the row, which is the universal unblock.

## Unblocking

Select the countdown in the change list and use **Delete selected**, or open
it and delete from the form. The next request from the public is no longer
blocked — there is no cache to clear and no process to restart.

## About the coloured status badges

`time_remaining_display` wraps its output in `<span>` elements carrying
`admin-status--green`, `admin-status--red` or `admin-status--gray`.

!!! warning "No stylesheet defines those classes"

    The package does not ship CSS for `admin-status--*`, and
    `SiteCountdownAdmin` declares no `class Media`. Out of the box the column
    renders as plain text — the markup is there, the colour is not.

If you want the colours, define them in your own admin override:

```django title="templates/admin/base_site.html"
{% extends "admin/base_site.html" %}

{% block extrastyle %}
  {{ block.super }}
  <style>
    .admin-status--green { color: #2e7d32; }
    .admin-status--red   { color: #c62828; }
    .admin-status--gray  { color: #757575; }
    .admin-status--bold  { font-weight: 700; }
  </style>
{% endblock %}
```

For that override to be found, your templates directory must come before app
directories in `TEMPLATES["DIRS"]`.

## Permissions

Standard Django model permissions apply — `django_countdown.add_sitecountdown`
and friends. Worth thinking through: whoever holds them can close the public
site.

Note the asymmetry with the middleware bypass. A staff user with change
permission can *schedule* downtime but, unless they are a superuser, will be
blocked out of the front end by their own countdown. They keep admin access
either way, because `/admin/` is never blocked.

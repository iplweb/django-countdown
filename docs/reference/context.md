# Template context

Two separate context surfaces: the variables the context processor adds to
*your* templates, and the context the middleware renders the maintenance page
with.

## Context processor

```python
"django_countdown.context_processors.countdown_context"
```

Adds two variables to every template rendered with a `RequestContext`.

| Variable | Type | Populated when |
|---|---|---|
| `active_countdown` | `SiteCountdown` or `None` | A countdown exists for the current site and has **not** expired |
| `maintenance_countdown` | `SiteCountdown` or `None` | The countdown has expired, maintenance is still running, and the request comes from an authenticated superuser |

The two are mutually exclusive — at most one is ever non-`None`. Both keys are
always present, so `{% if active_countdown %}` is safe without a `default`
filter.

### Decision table

| Condition | `active_countdown` | `maintenance_countdown` |
|---|---|---|
| No `SiteCountdown` for the site | `None` | `None` |
| `now < countdown_time` | the object | `None` |
| Window open, superuser | `None` | the object |
| Window open, anyone else | `None` | `None` — but the middleware has already returned 503 |
| `maintenance_until` has passed | `None` | `None` |
| Site cannot be resolved, or any other error | `None` | `None` (logged) |

The "anyone else" row only matters for requests the middleware lets through
anyway — an exempt path such as `/admin/`, or a project that registered the
context processor without the middleware.

### Usage

```django
{% if active_countdown %}
  <div class="alert">
    {{ active_countdown.message }}
    — closing in {{ active_countdown.time_remaining }}
  </div>
{% endif %}

{% if maintenance_countdown %}
  <div class="alert alert--warning">
    The public site is closed right now. You are seeing it because you are a
    superuser.
  </div>
{% endif %}
```

Both variables are ordinary model instances, so every method in
[`SiteCountdown`](model.md#methods) is available — `time_remaining`,
`maintenance_duration_minutes`, `is_indefinite`, and the rest.

!!! note "One query per rendered request"

    The processor runs a single `SiteCountdown.objects.get(site=...)` lookup,
    plus whatever `get_current_site()` costs (cached by the sites framework
    when `SITE_ID` is set). It is not memoised across templates within a
    request, but a `RequestContext` is built once, so the cost is per
    response, not per `{% include %}`.

### Failure behaviour

`SiteCountdown.DoesNotExist` is swallowed silently — the common case of "no
countdown configured". Any other exception is logged to the
`django_countdown.context_processors` logger with a traceback, and both
variables come back `None`. A template can never crash because of it.

## Blocked-page context

The middleware renders the maintenance template itself, with a context that
does **not** include your project's context processors' full output beyond
what `render()` normally provides.

| Variable | Type | Notes |
|---|---|---|
| `countdown` | `SiteCountdown` | The expired countdown that caused the block |
| `site` | `Site` | Resolved current site — `site.name` and `site.domain` are used by the shipped templates |
| `countdown_status_path` | `str` | Where the page polls for the site's return |
| `countdown_poll_interval` | `int` | Seconds between those polls; `0` renders the page without any |
| `countdown_return_url` | `str` | The page the visitor originally asked for, and where they are sent once the site is back. Taken from `request.get_full_path()` and validated to resolve inside the site |

Note the name: it is `countdown`, **not** `active_countdown`. A template
written for the banner will not work as a maintenance page without renaming.

```python
render(
    request,
    get_blocked_template(),
    {
        "countdown": countdown,
        "site": countdown.site,
        "countdown_status_path": get_status_path(),
        "countdown_poll_interval": get_poll_interval(),
        "countdown_return_url": get_return_url(request),
    },
    status=503,
)
```

The last three come from
[settings](settings.md#django_countdown_status_path) and the request itself.
If you render a maintenance template from your own view and omit them, the
page still renders — it just never notices that the site came back.

`get_return_url()` is not a synonym for `request.get_full_path()`: a path
beginning with `//`, or with a backslash the browser reads as a slash,
resolves as an address of its own and would send the visitor off the site
entirely. Such a path falls back to `/`. Some WSGI servers normalise those
paths away before Django sees them and some do not, so the check is made
here. If you pass your own value, the page validates it once more against
its own origin before navigating.

Because `render()` builds a `RequestContext`, your configured context
processors do run — including `countdown_context` itself, which returns
`None`/`None` here (the countdown has expired, and the visitor is not a
superuser). Do not rely on `active_countdown` inside a maintenance template;
use `countdown`.

What the shipped templates read:

| Expression | Used for |
|---|---|
| `countdown.message` | Headline block |
| `countdown.long_description` | Optional paragraph, omitted when empty |
| `countdown.maintenance_until` | Presence switches between the timer and the "no scheduled end" block |
| `countdown.maintenance_until.isoformat` | Target timestamp handed to the JavaScript timer |
| `countdown_poll_interval` | Presence switches the background poll and its status line on |
| `countdown_status_path` | Where that poll goes |
| `countdown_return_url` | Where the visitor is sent once the poll reports the site is back |
| `site.name` | `<title>` and footer |
| `LANGUAGE_CODE` | `<html lang="…">`, falling back to `en` — see [Translations](../guide/i18n.md) |

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

Note the name: it is `countdown`, **not** `active_countdown`. A template
written for the banner will not work as a maintenance page without renaming.

```python
render(
    request,
    get_blocked_template(),
    {"countdown": countdown, "site": current_site},
    status=503,
)
```

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
| `site.name` | `<title>` and footer |
| `LANGUAGE_CODE` | `<html lang="…">`, falling back to `en` — see [Translations](../guide/i18n.md) |

# Countdown banner

The banner is the announcement half of the package: a partial you include in
your own layout, which renders itself only while there is something to
announce.

```django title="templates/base.html"
{% include "django_countdown/countdown_banner.html" %}
```

Put it immediately after `<body>` — the banner is a full-width strip and
expects to sit above your content. When no countdown is active the partial
outputs nothing, so it costs one `if` per render and can stay in place
permanently.

!!! note "It needs the context processor"

    The partial reads `active_countdown` and `maintenance_countdown` from the
    template context. Without
    `django_countdown.context_processors.countdown_context` registered, both
    are undefined and the banner never appears. See
    [Installation](../getting-started/installation.md#3-context-processor).

## The two banners

One template, two mutually exclusive states — see
[Template context](../reference/context.md) for exactly when each variable is
populated.

### Announcement banner

Shown to **everyone** while `now < countdown_time`. It carries:

- the `message` as a headline;
- a live timer counting down to the cutoff (`id="countdown-timer"`);
- "you can keep working, but save your data regularly";
- the planned duration — "Estimated maintenance duration: 30 minutes" from
  `maintenance_duration_minutes()`, or an explicit "indefinite" warning when
  `maintenance_until` is empty.

When the timer hits zero it swaps to "Maintenance running — page will refresh
shortly" and reloads after three seconds. That reload is the request that
gets the 503.

### Maintenance banner

Shown to **superusers only**, while the window is open. It is deliberately
quieter — a single line reading "System under maintenance — {message}" plus a
timer to reopening (`id="maintenance-timer"`), or "Indefinite — remove the
countdown to unblock the site" when there is no end.

Its job is to stop you forgetting that the public is currently locked out
while you work.

## Styling

The partial loads its own stylesheet with
`{% static 'django_countdown/scss/countdown.css' %}` — plain CSS despite the
directory name, with no build step and no framework dependency.

!!! info "The `<link>` is emitted inside `<body>`"

    Browsers accept it, but it is a render-blocking stylesheet outside
    `<head>`. If that bothers you — or if you use a strict CSP or a hashed
    asset pipeline — copy the stylesheet reference into your own base
    template's `<head>` and override the partial (below) to drop it.

Hooks available without touching the template:

| Class | Applies to |
|---|---|
| `.countdown-banner` | Announcement strip |
| `.maintenance-banner` | Superuser maintenance strip |
| `.countdown-timer` | Live timer inside either strip |
| `.countdown-timer--indefinite` | Timer slot when there is no end time |
| `.countdown-message` | The `message` text |
| `.hide-on-print` | Set on both strips; hidden in print stylesheets |

There is also one piece of legacy adaptation: if the page contains an element
with `id="grp-header"` (Grappelli's admin header), the script adds
`has-countdown-banner` to `<body>` so you can offset a fixed header in your
own CSS.

## Overriding the template

Django resolves templates by name in loader order, so a file at
`django_countdown/countdown_banner.html` inside your own templates directory
wins over the packaged one:

```
your_project/
└── templates/
    └── django_countdown/
        └── countdown_banner.html
```

For that to work, your directory must be searched first:

```python title="settings.py" hl_lines="4 5"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        # ...
    },
]
```

`DIRS` is searched before app directories, so your copy shadows the package's.

Start from the
[original](https://github.com/iplweb/django-countdown/blob/main/src/django_countdown/templates/django_countdown/countdown_banner.html)
and edit it — the file is self-contained markup plus one inline script, with
no `{% extends %}` to reason about.

!!! tip "Or skip the partial entirely"

    The context variables are ordinary model instances. If you want the
    countdown inside an existing alert component, ignore the partial and read
    the object directly:

    ```django
    {% if active_countdown %}
      <div class="my-alert">
        {{ active_countdown.message }} —
        closing at {{ active_countdown.countdown_time }}
        ({{ active_countdown.time_remaining }} left)
      </div>
    {% endif %}
    ```

    `time_remaining` renders server-side and does not tick. Use it for
    non-JS contexts, or when a live timer would be noise.

## Where the banner will not appear

- **The Django admin** — admin templates do not include your base layout, so
  the banner is absent there unless you override `admin/base_site.html`
  yourself.
- **The maintenance page** — it is a standalone document with its own timer;
  see [Blocked page](blocked-page.md).
- **Anything rendered without a request context** — the context processor
  needs a request, so `render_to_string()` without one produces no banner.

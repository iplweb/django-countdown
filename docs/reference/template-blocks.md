# Template blocks

`django_countdown/blocked_base.html` is the extension point for the
maintenance page. It defines fifteen blocks — some structural, most of them
just the CSS classes on an element, so you can retarget the page at a
different framework without rewriting the markup.

```django
{% extends "django_countdown/blocked_base.html" %}
{% load static %}

{% block blocked_stylesheets %}
  <link rel="stylesheet" href="{% static 'css/site.css' %}">
{% endblock %}
```

## Structural blocks

| Block | Default | Purpose |
|---|---|---|
| `blocked_stylesheets` | *empty* | Everything that goes in `<head>` after the viewport meta. All three shipped variants override only this. |
| `blocked_body` | The whole page | Replaces the entire content of `<body>`. The timer script sits *outside* it and still runs. |
| `blocked_header_icon_left` | `<div class="maintenance-icon icon-key"><span class="fi-wrench"></span></div>` | Icon left of the headline |
| `blocked_header_icon_right` | `<div class="maintenance-icon icon-cog"><span class="fi-widget"></span></div>` | Icon right of the headline |

The default icons use Foundation icon classes (`fi-*`), which is why the
plain variant shows empty boxes unless its own CSS styles them. Override both
blocks — with an emoji, an inline SVG, or nothing at all — when you are not
on Foundation.

## Class blocks

Each of these replaces the `class` attribute of one element. The element,
its content and its `id` stay put.

| Block | Default value | Element |
|---|---|---|
| `blocked_body_class` | `maintenance-page` | `<body>` |
| `blocked_container_class` | `maintenance-container` | Outer wrapper `<div>` |
| `blocked_header_class` | `maintenance-header` | Header row holding icons and title |
| `blocked_title_class` | `maintenance-title` | `<h1>` — "System under maintenance" |
| `blocked_message_class` | `maintenance-message` | `countdown.message` |
| `blocked_description_class` | `maintenance-description` | `countdown.long_description`, rendered only when non-empty |
| `blocked_timer_class` | `countdown-timer` | Timer wrapper, bounded window |
| `blocked_label_class` | `countdown-label` | "Estimated end of maintenance in:" |
| `blocked_timer_class_indef` | `countdown-timer countdown-timer--indefinite` | Timer wrapper, indefinite window |
| `blocked_label_class_indef` | `countdown-label` | "Maintenance has no scheduled end." |
| `blocked_footer_class` | `maintenance-footer` | Footer with the apology and `site.name` |

The `_indef` pair exists because the two states need different styling —
usually a calmer treatment for the case where there is no number to show.

## Element IDs the script depends on

The countdown script is outside every block and cannot be overridden without
replacing the whole template. It looks for two IDs, present only when
`countdown.maintenance_until` is set:

| ID | Element | Written by the script |
|---|---|---|
| `countdown-display` | Timer wrapper | — (marker only) |
| `countdown-value` | Inner `<div>` | The formatted remaining time, then "Maintenance finished!" |

If you override `blocked_body`, keep `id="countdown-value"` on some element
or the timer silently does nothing — `document.getElementById` returns
`null` and the first tick throws.

## Structure at a glance

```html
<body class="{{ blocked_body_class }}">
  <div class="{{ blocked_container_class }}">
    <div class="{{ blocked_header_class }}">
      {{ blocked_header_icon_left }}
      <h1 class="{{ blocked_title_class }}">System under maintenance</h1>
      {{ blocked_header_icon_right }}
    </div>
    <div class="{{ blocked_message_class }}">{{ countdown.message }}</div>
    <div class="{{ blocked_description_class }}">{{ countdown.long_description }}</div>

    <!-- one of the two, depending on maintenance_until -->
    <div class="{{ blocked_timer_class }}" id="countdown-display">
      <div class="{{ blocked_label_class }}">Estimated end of maintenance in:</div>
      <div id="countdown-value">…</div>
    </div>
    <div class="{{ blocked_timer_class_indef }}">
      <div class="{{ blocked_label_class_indef }}">Maintenance has no scheduled end.</div>
      <div>The site will become available once an administrator unblocks it.</div>
    </div>

    <div class="{{ blocked_footer_class }}">…{{ site.name }}</div>
  </div>
</body>
<script>…</script>
```

Braces above stand for block *output*, not template variables — this is the
rendered shape, not copy-pastable source.

## Worked example: Bootstrap-style overrides

How the shipped Bootstrap variant does it, condensed:

```django title="templates/django_countdown/blocked_bootstrap.html"
{% extends "django_countdown/blocked_base.html" %}

{% block blocked_stylesheets %}
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <style>
    body.maintenance-page { min-height: 100vh; display: flex; align-items: center; }
    .maintenance-container { max-width: 600px; margin: auto; text-align: center; }
  </style>
{% endblock %}

{% block blocked_header_icon_left %}<i class="bi bi-wrench-adjustable"></i>{% endblock %}
{% block blocked_header_icon_right %}<i class="bi bi-gear"></i>{% endblock %}
```

It keeps the default class names and styles them, rather than swapping every
class block — usually the shorter path. Reach for the class blocks when your
framework is utility-first and the classes *are* the styling.

## The banner has no blocks

`countdown_banner.html` is a flat partial with no `{% extends %}` and no
`{% block %}`. To change it, shadow the whole file from your own templates
directory — see [Countdown banner](../guide/banner.md#overriding-the-template).

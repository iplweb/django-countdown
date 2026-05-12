# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-05-12

### Added
- **i18n**: every user-visible string now flows through `gettext_lazy` /
  `{% trans %}`, with full Polish translations shipped in
  `django_countdown/locale/pl/LC_MESSAGES/django.{po,mo}`.
- **`manage.py start_countdown`** management command — interactive by
  default (asks how long the banner shows, then how long service mode
  lasts), or non-interactive via `--banner +5m --service +30m --message …
  --noinput`. Service duration accepts `indefinite`/`forever`/`inf` to
  keep the site blocked until an admin removes the countdown.
- **Indefinite maintenance mode**: when `maintenance_until` is `None` the
  site stays blocked indefinitely. New `SiteCountdown.is_indefinite()`
  helper + admin column; banner and blocked templates render an
  "indefinite — remove the countdown to unblock" affordance instead of a
  broken counter.
- **CSS-framework-agnostic blocked-page themes**: three variants —
  `blocked.html` (plain, default — ships its own stylesheet, no Bootstrap
  / Foundation / Tailwind required), `blocked_foundation.html`,
  `blocked_bootstrap.html` — all extending a shared `blocked_base.html`
  so themes inherit translations automatically. Pick one via the new
  `DJANGO_COUNTDOWN_BLOCKED_TEMPLATE` setting.
- **Example app discovery page**: the example project now has a real
  `/` page listing all template variants with one-click previews
  (`/preview/<plain|foundation|bootstrap>/[indefinite/]`) and a
  `/healthz/` endpoint for confirming the middleware blocks correctly.
- `SiteCountdown` model + admin (extracted from
  [iplweb/bpp](https://github.com/iplweb/bpp) @ 75f3c70f7) with
  `countdown_time` and optional `maintenance_until`.
- `CountdownBlockingMiddleware` returning HTTP 503 for non-superuser
  requests once the countdown has expired and maintenance has not yet
  ended.
- `countdown_context` context processor exposing `active_countdown` /
  `maintenance_countdown` to templates.
- Template partials: `countdown_banner.html` and `blocked.html`.

### Changed
- `countdown_banner.html` no longer depends on `django-compressor`; it
  just `{% static %}`-loads the package stylesheet.
- `blocked.html` no longer pulls Foundation Sites or foundation-icons by
  default. Use `blocked_foundation.html` if you want that look.
- All hard-coded Polish field labels, help-texts, and admin headings in
  the model + admin migrated to English as the source language, with
  Polish kept as a first-class translation.

### Fixed
- `admin.time_remaining_display` two `format_html()` calls with no
  substitutions raised `TypeError` on Django 6.0 (strict signature).
  Replaced with `mark_safe()` for the literal-HTML branches.

### Migrations
- `0005_alter_sitecountdown_options_and_more.py` records the English
  field metadata. Running `migrate` is required after upgrading.

## [0.1.0]

Never released to PyPI. Skipped in favour of 0.2.0, which is the first
public release.

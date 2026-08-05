# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Until now the package could only ever *create* a countdown. There was no
scriptable way to remove one, adjust one that was already running, or ask what
the current state was — the documentation's own answer was a `manage.py shell`
one-liner, composed while the site was down.

### Added
- **`stop_countdown`** — deletes countdowns and reopens the site. In indefinite
  mode this is the only way back. Sweeps every site by default, because it runs
  when something is blocked and you should not have to work out which `SITE_ID`
  is to blame first; `--site-id` narrows it. Nothing to delete is a success, not
  an error.
- **`show_countdown`** — reports which phase each countdown is in and how long
  until the next transition. Always exits `0`, including when the site is
  blocked, because that is a normal state for this package rather than a failure
  of the command. `--json` emits a machine-readable array for monitoring and
  deploy gates.
- **`extend_countdown`** and **`shorten_countdown`** — move a boundary of a
  window already in flight. `--banner` moves when the site closes and slides the
  whole schedule, preserving the window's length; `--service` moves when it
  reopens. Both default to the current site, with `--all` to widen: they edit a
  schedule rather than ending one, so a wrong target would move another tenant's
  window.
- **`extend_countdown --at-least 5m`** — raises a floor rather than adding time,
  so repeated runs absorb instead of accumulating and a retry can never
  overshoot. This makes a dead man's switch possible: a deploy loop holds the
  window open while it works, and if the deploy dies the site reopens by itself.

### Changed
- `start_countdown`'s indefinite-mode warning now names `stop_countdown` instead
  of pointing at the admin and `manage.py shell`.

### Fixed
- Documentation stated "There is no `stop_countdown`" and built a deploy recipe
  on shell one-liners. Both are replaced, and the guide now lays the heartbeat
  and indefinite-window patterns side by side rather than declaring a winner —
  they fail in opposite directions, and the heartbeat's own host is often the
  machine being deployed.

## [0.2.1] — 2026-05-13

Example-project polish only — the published `django_countdown` wheel is
unchanged from 0.2.0. No migration or code change is required for users
of the package.

### Fixed
- Example app's discovery page (`example/`) referenced the management
  command as `start-countdown` (hyphen) in three places. Django commands
  use the underscored filename (`start_countdown`), so copy-pasting the
  snippets failed. All three snippets corrected.

### Added
- Example app is now fully translatable end-to-end. Every user-visible
  string on the discovery page goes through `{% trans %}` /
  `{% blocktrans %}`, the preview-variant labels in `views.py` use
  `gettext_lazy`, and a complete Polish catalog ships at
  `example/example_project/locale/pl/LC_MESSAGES/django.{po,mo}`. Set
  `Accept-Language: pl` (or run with `LANGUAGE_CODE = "pl"`) to see it.
- "Refresh this page after running the command" hints next to both
  CLI-invocation blocks on the discovery page, so demo users notice the
  banner appears on the next request.

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

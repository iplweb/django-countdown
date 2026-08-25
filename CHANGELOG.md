# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- The maintenance page now waits for the site to come back on its own. It
  polls a small status endpoint in the background and, the moment the site is
  unblocked, sends the visitor to the page they originally asked for. A
  deployment window is three states, not one — the old server still serving,
  nothing serving while the container is replaced, the new server up — and
  the page now tells them apart and says which one it is looking at.
- `DJANGO_COUNTDOWN_STATUS_PATH` (default `/__countdown_status__/`) — the
  path where `CountdownBlockingMiddleware` answers that poll. It is matched
  before anything else in `process_request`, so it needs no `URLconf` entry
  and answers even while the rest of the site is blocked. The response is
  always HTTP 200, with the state in the body behind a
  `"service": "django-countdown"` marker: a reverse proxy with no upstream
  answers 5xx on its own, so a status endpoint using those codes could not be
  told apart from the proxy speaking for it.
- `DJANGO_COUNTDOWN_POLL_INTERVAL` (default `10` seconds) — how often the
  page checks, scheduled with ±20 % of jitter so the end of a window does not
  wake every waiting tab into a stampede against a server that has just
  started. `0` turns the polling off.
- The destination of that return trip is validated against the site's own
  origin, on the server and again in the browser before navigating. A path
  beginning with `//` — or with a backslash, which browsers read as a slash —
  resolves as an address of its own; unchecked, the maintenance page would be
  an unusually effective open redirect, since it is a page visitors are told
  to trust and wait on. Django's development server and gunicorn normalise
  such paths away before the request arrives, uWSGI does not, and a library
  cannot know which one it runs under.
- `blocked_status_line` and `blocked_status_class` template blocks for the
  new status line, and `countdown_status_path` / `countdown_poll_interval` /
  `countdown_return_url` in the blocked-page context.

### Changed
- The maintenance page no longer reloads itself blindly — neither three
  seconds after the timer expires nor every 30 seconds during an indefinite
  window. Both reloads assumed the site would be back by the time they fired;
  when it was not, they dropped the visitor on the proxy's error page, where
  no script was left to try again and the only way back was a manual refresh.
  The timer now only reports, and navigation happens solely on a confirmed
  answer from the server.
- When the planned end passes and the site is still down, the timer's label
  switches from "Estimated end of maintenance in:" to "Planned end exceeded
  by:" and counts the overrun, instead of announcing "Maintenance finished!"
  for something that plainly has not finished.
- Each poll feeds the server's current `maintenance_until` back into the
  timer, so extending a running window with `extend_countdown` corrects pages
  that are already open, without a reload.
- The blocking decision moved into `get_blocking_countdown()`, shared by the
  middleware and the status endpoint. The page a browser is shown and the
  answer it polls for now come from one function and cannot disagree.

## [0.3.1] — 2026-08-07

A metadata-only release: no source changes, just the declared support for
Django 6.1 plus the CI and packaging fixes listed below.

### Added
- Support for Django 6.1, released 2026-08-05. The CI matrix gains
  Django 6.1 on Python 3.12, 3.13 and 3.14 — 6.1 requires Python 3.12 or
  newer, so the 3.10/3.11 cells stay 5.2-only. No source changes were
  needed; the `Framework :: Django :: 6.1` trove classifier is declared.

### Changed
- Trove classifier moved from `Development Status :: 3 - Alpha` to
  `4 - Beta`. The command set now covers the whole countdown lifecycle, tests
  run across Python 3.10–3.14 × Django 5.2/6.0/6.1, and the documented
  behaviour is under test — the API is stable enough to depend on. Takes
  effect on PyPI with the next release; 0.3.0 shipped as Alpha.

### Fixed
- CI actions bumped off Node 20, which GitHub has deprecated:
  `actions/checkout@v5`, `upload-artifact@v7`, `download-artifact@v8`,
  `deploy-pages@v5`, `setup-uv` v9. Note that `upload-artifact@v5` and
  `download-artifact@v5` are still Node 20 — the jump to v7/v8 is what actually
  moves them.
- `setup-uv`'s cache key was never invalidated: it globs for `uv.lock`, which
  this repository gitignores (a library pins nothing), so the file never reached
  the runner and nothing ever matched. Keyed on `pyproject.toml` instead, with a
  per-job `cache-suffix`. The suffix is not cosmetic: `setup-uv` runs before
  `uv python install`, so its key carries the *runner's* Python rather than the
  matrix one, and all eight matrix jobs would otherwise compute an identical key
  and race to reserve it.

## [0.3.0] — 2026-08-05

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

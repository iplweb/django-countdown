# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial extraction from [iplweb/bpp](https://github.com/iplweb/bpp) @ 75f3c70f7.
- `SiteCountdown` model with `countdown_time` + optional `maintenance_until`.
- `CountdownBlockingMiddleware` that returns HTTP 503 for non-superuser
  requests once the countdown has expired and maintenance has not yet ended.
- `countdown_context` context processor exposing `active_countdown` /
  `maintenance_countdown` to templates.
- Template partials: `countdown_banner.html` and `blocked.html`.
- Django admin integration for `SiteCountdown`.

### Fixed
- `admin.time_remaining_display` two `format_html()` calls with no
  substitutions raised `TypeError` on Django 6.0 (strict signature). Replaced
  with `mark_safe()` for the literal-HTML branches.

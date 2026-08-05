# `stop_countdown` — design

**Date:** 2026-08-05
**Status:** approved, ready for planning
**Branch:** `worktree-stop-countdown`

## Problem

`django-countdown` ships exactly one management command, `start_countdown`. There
is no scriptable way to undo what it does. The package admits the gap in its own
success message (`start_countdown.py:368-370`):

> ⚠ Indefinite mode — remove the countdown via admin or `manage.py shell` to
> unblock the site.

So the recovery path for a blocked site is the Django admin or a shell one-liner.
`docs/guide/multisite.md` repeats the same advice, telling multi-tenant operators
to run `SiteCountdown.objects.all().delete()` by hand.

That is the wrong shape for the situation it serves. Removing a countdown is a
rescue action taken while the site is down; it should be one command, safe to put
in a runbook or a deploy hook.

## Solution

A `stop_countdown` management command that deletes `SiteCountdown` rows.

### Naming

`stop_countdown`, for symmetry with `start_countdown`. The pair reads as a pair
in `manage.py help`, and the two sort next to each other under the
`[django_countdown]` heading.

### Semantics: delete, not soft-close

The command issues a real `DELETE`.

A site can be unblocked two ways: remove the row (`middleware.py:49-50` lets the
request through on `DoesNotExist`), or push `maintenance_until` into the past
(`middleware.py:53-54` lets it through once maintenance is finished). Both
unblock. Deleting is the better default because it leaves a clean slate: a
surviving row would still count as "an existing countdown" and force the next
`start_countdown` to be run with `--force` (`start_countdown.py:299-305`), and
would clutter the admin list with rows that no longer mean anything.

No soft-close variant is offered. Anyone who wants the history can read it in the
admin before removing the row.

### Scope: all sites by default

Without arguments the command removes **every** `SiteCountdown`. `--site-id N`
narrows it to one site.

This is deliberately the opposite default from `start_countdown`, which targets
the current site. The two commands answer different questions:

- `start_countdown` is planning work. Picking a specific site is the point.
- `stop_countdown` is rescue work. It runs when the site is down, and it must not
  require the operator to first work out which `SITE_ID` is to blame. A per-site
  default invites the failure where the countdown is cleared for `SITE_ID=1`
  while a row attached to a different `Site` — often the `example.com` row that
  `migrate` creates and nobody edits — keeps traffic blocked.

For single-site installations, which is most of them, "all countdowns" and "this
site's countdown" name the same single row, so the default costs nothing there.

### Rejected: making `SiteCountdown` a singleton

Dropping the `Site` foreign key would simplify the middleware and the context
processor, but it is a breaking change to a published package (0.2.1): it needs a
destructive migration and a rewrite of `middleware.py:42-50`,
`context_processors.py:17-18`, `admin.py` and the templates. It also removes a
capability that `django.contrib.sites` exists to provide — one Django serving
several domains, where maintenance affects only one of them
(`docs/guide/multisite.md`).

If the singleton is still wanted, it is its own decision for 0.3 or 1.0, with a
migration and a breaking-change note. It is not a rider on this command.

## Behaviour

```console
$ ./manage.py stop_countdown [--site-id N] [--noinput]
```

| Option | Meaning |
|---|---|
| `--site-id N` | Remove only this site's countdown. Default: remove all. |
| `--noinput`, `--no-input` | Never prompt. Required when stdin is not a TTY. |

No `--force`. In `start_countdown` that flag means "replace the existing row and
skip the final confirmation"; here `--noinput` already covers skipping the
confirmation, and there is nothing to replace.

### Sequence

1. **Resolve the target queryset.**
   - `--site-id N` given: `SiteCountdown.objects.filter(site_id=N)`. If no `Site`
     with that id exists, raise `CommandError` — a typo in the id must not be
     reported as "nothing to remove". This mirrors
     `start_countdown._resolve_site` (`start_countdown.py:210-215`).
   - Otherwise: `SiteCountdown.objects.all()`.
2. **Nothing to do.** If the queryset is empty, print a notice and return.
   Exit status 0 — the command is idempotent, so it can go in a deploy script
   without `|| true`.
   This check runs **before** the TTY check in step 4, so a non-TTY run with
   nothing to remove is a clean no-op rather than an error. There is nothing to
   confirm, so refusing to proceed would be noise.
3. **Show what will go.** One line per countdown: site domain, message,
   `countdown_time`, and current state — `blocking now` (expired and maintenance
   unfinished), `banner showing` (not yet expired), or `finished` (maintenance
   window already over).
4. **Confirm.** Unless `--noinput`, ask `Remove N countdown(s)? [y/N]`, defaulting
   to no. Any answer other than `y`/`yes` prints `Aborted.` and returns without
   deleting, exit status 0.
   If stdin is not a TTY and `--noinput` was not passed, raise `CommandError`
   naming `--noinput` as the fix, matching `start_countdown.py:251-254`.
5. **Delete.** A single queryset `DELETE`.
6. **Report.** `✓ Removed N countdown(s).` followed by the affected domains.

### Exit statuses

`0` for success, no-op, and user abort. `CommandError` (Django exits `1`) for an
unknown `--site-id` and for a non-TTY run without `--noinput`.

## Refactor: shared CLI helpers

`start_countdown.py` keeps four helpers that `stop_countdown` needs too:
`format_when` (module-level), and `_interactive`, `_ask`, `_resolve_site`
(methods on `Command` that never touch `self`).

Move all four to `src/django_countdown/management/commands/_cli.py` as module
functions `format_when`, `is_interactive`, `ask`, `resolve_site`, and update
`start_countdown` to call them.

Django's `find_commands()` filters out module names starting with `_`, so `_cli`
will not appear in `manage.py help`.

This does not break the existing tests: `tests/test_start_countdown.py` imports
only `parse_relative`, `parse_service` and `INDEFINITE_TOKENS`, all of which stay
in `start_countdown.py`.

## Files

| File | Change |
|---|---|
| `src/django_countdown/management/commands/stop_countdown.py` | new |
| `src/django_countdown/management/commands/_cli.py` | new — shared helpers |
| `src/django_countdown/management/commands/start_countdown.py` | use `_cli`; success message points at `stop_countdown` instead of admin/shell |
| `tests/test_stop_countdown.py` | new |
| `CHANGELOG.md` | new entry |

## Testing

New file `tests/test_stop_countdown.py`, following the conventions in
`tests/test_start_countdown.py` (`call_command`, `StringIO`, `pytest.mark.django_db`).

Cases:

1. No countdowns at all, no `--noinput` — succeeds rather than raising, because
   the empty check precedes the TTY check.
2. One countdown, no arguments — removed.
3. Countdowns on several sites, no arguments — all removed.
4. `--site-id` — removes only that site's countdown; the others survive.
5. `--site-id` naming a `Site` that does not exist — `CommandError`.
6. `--site-id` naming a real `Site` that has no countdown — no-op, and other
   sites' countdowns survive. This is what proves `--site-id` does not silently
   fall back to the all-sites path.
7. A countdown exists, not a TTY, no `--noinput` — `CommandError`, and the row
   survives.
8. Interactive confirmation accepted, and refused — refusal leaves the row in
   place. Patch `is_interactive`/`ask` with `pytest-mock`.
9. Output names the removed domains.
10. Integration: middleware returns 503, `stop_countdown` runs, middleware returns
    200 for the same request.

## Out of scope for this branch

`docs/`, `mkdocs.yml` and `README.md` are being rewritten concurrently on another
branch and are not present in this worktree. Documentation lands as a follow-up
once that work is merged:

- `docs/guide/management-command.md` — retitle to the plural, document
  `stop_countdown`.
- `docs/guide/multisite.md:72-108` — currently states "There is no 'all sites'
  mode" and gives a `manage.py shell` one-liner for reopening every site. Both
  are superseded by this command.
- `mkdocs.yml` nav, and the README command section.

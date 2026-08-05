# Countdown lifecycle commands — design

**Date:** 2026-08-05
**Status:** draft, awaiting approval
**Branch:** `worktree-stop-countdown`

## Problem

`django-countdown` ships exactly one management command, `start_countdown`. It
can create a countdown and nothing else. There is no scriptable way to remove
one, to adjust one that is already running, or even to ask what the current state
is.

The package admits the first gap in its own success message
(`start_countdown.py:368-370`):

> ⚠ Indefinite mode — remove the countdown via admin or `manage.py shell` to
> unblock the site.

`docs/guide/multisite.md` repeats the advice, telling multi-tenant operators to
run `SiteCountdown.objects.all().delete()` by hand.

That is the wrong shape for the situations these actions serve. Every one of them
happens under time pressure — the site is closing, or already closed, and the
window is not going to plan. They should be single commands, safe to put in a
runbook, not shell one-liners composed while the site is down.

## The command set

| Command | Status | Purpose |
|---|---|---|
| `start_countdown` | exists | Create or replace a countdown. |
| `stop_countdown` | new | Delete countdowns. Reopen the site. |
| `extend_countdown` | new | Push a phase boundary later. |
| `shorten_countdown` | new | Pull a phase boundary earlier. |
| `show_countdown` | new | Report the current phase and time to the next transition. |

All five follow `<verb>_countdown`, so they group together in `manage.py help`
under `[django_countdown]` and read as a family.

### Why not one `adjust_countdown` with a signed duration

`extend` and `shorten` are the same operation with opposite signs, so one command
taking `+15m` / `-15m` is tempting. Two commands are better here for two reasons.

`parse_relative` currently rejects negative input — `-5m` is in the
rejected-input list in `tests/test_start_countdown.py`. Supporting signed
durations means loosening a regex that `start_countdown` also depends on, for no
gain.

More importantly, these commands run during an incident. `shorten_countdown
+15m` cannot be misread; `adjust_countdown -15m` can, and the failure mode of a
sign error is closing the site fifteen minutes early instead of late.

The two commands share an implementation (see *Shared helpers*), so the
duplication is in the CLI surface only, which is exactly where the redundancy is
worth paying for.

## Shared conventions

These hold for all four new commands.

**Scope.** With no arguments a command targets **every** `SiteCountdown`.
`--site-id N` narrows it to one site.

This is deliberately the opposite default from `start_countdown`, which targets
the current site. The two kinds of command answer different questions:

- `start_countdown` is planning work. Picking a specific site is the point.
- The new commands are incident work. They run when something is wrong, and must
  not require the operator to first work out which `SITE_ID` is to blame. A
  per-site default invites the failure where the countdown is cleared for
  `SITE_ID=1` while a row attached to a different `Site` — often the
  `example.com` row that `migrate` creates and nobody edits — keeps traffic
  blocked.

For single-site installations, which is most of them, "all countdowns" and "this
site's countdown" name the same single row, so the default costs nothing there.

If `--site-id` names a `Site` that does not exist, the command raises
`CommandError`. A typo in the id must not be reported as "nothing to do". This
mirrors `start_countdown._resolve_site` (`start_countdown.py:210-215`).

**Confirmation.** The three mutating commands (`stop`, `extend`, `shorten`) print
what they are about to change, then ask for confirmation, defaulting to no.
`--noinput` / `--no-input` skips the prompt. If stdin is not a TTY and `--noinput`
was not passed, they raise `CommandError` naming `--noinput` as the fix, matching
`start_countdown.py:251-254`.

`show_countdown` never prompts and takes no `--noinput`.

**Empty target.** If the target queryset is empty, the command prints a notice and
returns successfully. The commands are idempotent so they can go in a deploy
script without `|| true`.

This check runs **before** the TTY check, so a non-TTY run with nothing to do is a
clean no-op rather than an error. There is nothing to confirm, so refusing to
proceed would be noise.

**Exit statuses.** `0` for success, no-op and user abort. `CommandError` (Django
exits `1`) for an unknown `--site-id`, for a non-TTY run without `--noinput`, and
for the per-command guard violations listed below.

**All-or-nothing.** When a command targets several sites and any one of them fails
a guard, nothing is written. Guards are evaluated for every target first, and the
whole run aborts with `CommandError` naming the offending sites. A partially
applied schedule change is worse than a refused one.

---

## `stop_countdown`

```console
$ ./manage.py stop_countdown [--site-id N] [--noinput]
```

Deletes rows. That is the whole command.

### Delete, not soft-close

A site can be unblocked two ways: remove the row (`middleware.py:49-50` lets the
request through on `DoesNotExist`), or push `maintenance_until` into the past
(`middleware.py:53-54` lets it through once maintenance is finished). Both
unblock.

Deleting is the better default because it leaves a clean slate. A surviving row
would still count as "an existing countdown" and force the next `start_countdown`
to be run with `--force` (`start_countdown.py:299-305`), and would clutter the
admin list with rows that no longer mean anything.

No soft-close variant is offered. Anyone who wants the history can read it in the
admin before removing the row.

### No `--force`

In `start_countdown`, `--force` means "replace the existing row and skip the final
confirmation". Here `--noinput` already covers skipping the confirmation, and
there is nothing to replace.

### Sequence

1. Resolve the target queryset (see *Scope*).
2. If empty, print a notice and return.
3. List what will go: one line per countdown with site domain, message,
   `countdown_time`, and current phase.
4. Confirm unless `--noinput`. Any answer other than `y`/`yes` prints `Aborted.`
   and returns without deleting.
5. A single queryset `DELETE`.
6. Report `✓ Removed N countdown(s).` and the affected domains.

---

## `extend_countdown` and `shorten_countdown`

```console
$ ./manage.py extend_countdown   (--banner +15m | --service +20m) [--site-id N] [--noinput]
$ ./manage.py shorten_countdown  (--banner +15m | --service +20m) [--site-id N] [--noinput]
```

Both take a **positive** duration in the existing `+<N>[s|m|h|d]` syntax, parsed
by the existing `parse_relative`. Exactly one of `--banner` / `--service` is
required; passing both or neither is a `CommandError`. Allowing both at once
would raise the question of whether the banner shift also drags the service edge,
and there is no answer that is obvious to a reader.

### Which edge: `--banner` vs `--service`

"Extend the countdown" is ambiguous, because the model has two time boundaries,
and both are genuinely extended in practice — just in different situations. The
flags reuse `start_countdown`'s vocabulary, and mean the same thing they mean
there:

```
    now              countdown_time            maintenance_until
     │◄─── --banner ────►│◄────── --service ──────►│
     │                   │                         │
  announced          site closes              site reopens
```

- `--banner` moves the moment the site **closes**. *"We are not ready — hold off
  fifteen more minutes."*
- `--service` moves the moment the site **reopens**. *"The migration is taking
  longer than planned."* This is the one you reach for while already down.

### Effects

`D` is the parsed duration.

| Command | Flag | `countdown_time` | `maintenance_until` |
|---|---|---|---|
| `extend` | `--banner` | `+= D` | `+= D` (if set) |
| `extend` | `--service` | unchanged | `+= D` |
| `shorten` | `--banner` | `-= D` | `-= D` (if set) |
| `shorten` | `--service` | unchanged | `-= D` |

`--banner` slides the **whole schedule**, preserving the length of the
maintenance window. This follows from how `start_countdown` defines the window:
`--service` is measured from `countdown_time`, not from now
(`start_countdown.py:274-276`), so the window is a duration hanging off the
closing time. Moving the closing time without moving the window would silently
shrink or grow it, which nobody asks for when they say "start fifteen minutes
later".

Moving one edge alone is what `--service` is for.

### Guards

Each raises `CommandError` with a message naming the alternative command:

| Condition | Reason |
|---|---|
| `countdown_time is None` | Nothing is scheduled. Use `start_countdown`. |
| `--banner` on an already-expired countdown | The banner phase is over; the site is closed. Sliding it would reopen the site and replay the banner. Use `start_countdown --force` to reschedule, or `stop_countdown` to reopen now. |
| `shorten --banner` landing at or before now | `countdown_time` must stay in the future — the same invariant `models.py:80-88` enforces. |
| `--service` when `maintenance_until is None` | The window is indefinite; it has no end to move. Use `start_countdown --force` to give it one, or `stop_countdown` to reopen now. |
| `shorten --service` landing at or before `countdown_time` | The window would end before it starts — the invariant at `models.py:89-97`. To reopen immediately, use `stop_countdown`. |

### Persistence: why not `full_clean()`

`SiteCountdown.clean()` (`models.py:80-88`) rejects **any** `countdown_time` in
the past. Once a countdown has expired — which is to say, whenever the site is
actually down — the object can no longer pass `full_clean()` at all, no matter
what is being changed.

That is precisely the state in which `extend_countdown --service` is most likely
to be run. So these commands must not call `full_clean()`. They validate
explicitly via the guards above, which reproduce exactly the two invariants
`clean()` enforces, and then persist with:

```python
countdown.save(update_fields=["countdown_time", "maintenance_until", "updated_at"])
```

`updated_at` is `auto_now`, and Django writes only the named columns when
`update_fields` is given, so it has to be listed explicitly or the timestamp
silently goes stale.

### Absolute retargeting is out of scope

There is no `--banner 2026-08-05T14:00` mode. Setting boundaries to absolute times
is what `start_countdown --force` already does, including full validation.
`extend`/`shorten` exist for relative nudges to a running schedule.

### Sequence

1. Resolve the target queryset.
2. If empty, print a notice and return.
3. Compute the new values for every target and evaluate all guards. Any violation
   aborts the whole run (see *All-or-nothing*).
4. Show a before → after line per site.
5. Confirm unless `--noinput`.
6. Save each row with `update_fields`.
7. Report the new schedule.

---

## `show_countdown`

```console
$ ./manage.py show_countdown [--site-id N] [--json]
```

Read-only. Reports, for each countdown, which phase it is in and how long until
the next transition. Never prompts, never writes, always exits `0` — including
when the site is blocked. Monitoring tools should read the payload, not the exit
status, because "blocked" is a normal state for this package and not a failure of
the command.

### Phases

| Phase | Condition | Next transition |
|---|---|---|
| `unscheduled` | `countdown_time is None` | none |
| `banner` | `now < countdown_time` | site closes at `countdown_time` |
| `blocked` | `countdown_time <= now < maintenance_until` | site reopens at `maintenance_until` |
| `blocked_indefinite` | `countdown_time <= now`, `maintenance_until is None` | none — needs `stop_countdown` |
| `finished` | `now >= maintenance_until` | none — row is stale |

These are the same conditions the middleware branches on
(`middleware.py:52-61`), so the report describes what visitors actually get
rather than a parallel guess at it.

### Human output

```
example.com — Scheduled maintenance
  phase   banner showing
  next    site closes 2026-08-05 09:15:00 CEST (in 12 min 30 sec)
  then    site reopens 2026-08-05 09:45:00 CEST (30 min window)

tenant-b.example.com — Database migration
  phase   blocked — maintenance running
  next    site reopens 2026-08-05 09:20:00 CEST (in 8 min)
```

`blocked_indefinite` reports `next  never — run stop_countdown to reopen`.
`finished` reports that the window is over and the row is stale, and names
`stop_countdown` as the way to clear it.

With no countdowns it prints a single line saying so, and exits `0`.

### `--json`

Emits a JSON array to stdout, one object per countdown, with the machine-readable
phase key from the table above:

```json
[{"site_id": 1, "domain": "example.com", "message": "Scheduled maintenance",
  "phase": "banner", "countdown_time": "2026-08-05T09:15:00+02:00",
  "maintenance_until": "2026-08-05T09:45:00+02:00",
  "next_event": "site_closes", "seconds_to_next": 750}]
```

`next_event` is `site_closes`, `site_reopens` or `null`. `seconds_to_next` is
`null` when there is no next transition. This is the reason a status command is
worth having as a command rather than an admin page — it is the piece a
monitoring check or a deploy gate can consume.

---

## Refactor: shared helpers

### `management/commands/_cli.py` (new)

`start_countdown.py` keeps four helpers the new commands also need:
`format_when` (module-level), and `_interactive`, `_ask`, `_resolve_site`
(methods on `Command` that never touch `self`).

Move all four there as module functions `format_when`, `is_interactive`, `ask`,
`resolve_site`, and update `start_countdown` to call them.

Django's `find_commands()` filters out module names starting with `_`, so `_cli`
will not appear in `manage.py help`.

The module also gains the machinery the four new commands share: target
resolution from `--site-id`, the empty-target notice, the TTY check, the
confirmation prompt, and phase classification. `extend_countdown` and
`shorten_countdown` are the same command with an opposite sign, so they are built
on a common base class parameterised by that sign — each concrete command
supplies only its name, help text and direction.

This does not break the existing tests: `tests/test_start_countdown.py` imports
only `parse_relative`, `parse_service` and `INDEFINITE_TOKENS`, all of which stay
in `start_countdown.py`.

### `django_countdown/utils.py` (new)

`SiteCountdown.time_remaining()` (`models.py:99-121`) formats a duration as
`"2 days 3 h 5 min"`, but only ever for `countdown_time`. `show_countdown` needs
the same formatting for the maintenance side too.

Extract the formatting into `format_duration(seconds)` in a package-level
`utils.py` and have `time_remaining()` delegate to it. It lives at package level,
not in `management/`, because the model must not import from the command layer.

The existing `gettext` msgids (`"%(n)d days"`, `"%(n)d h"`, `"%(n)d min"`,
`"%(n)d sec"`) move unchanged, so the compiled catalogues stay valid — `.po`
files carry source line numbers as comments only.

## Files

| File | Change |
|---|---|
| `src/django_countdown/management/commands/stop_countdown.py` | new |
| `src/django_countdown/management/commands/extend_countdown.py` | new |
| `src/django_countdown/management/commands/shorten_countdown.py` | new |
| `src/django_countdown/management/commands/show_countdown.py` | new |
| `src/django_countdown/management/commands/_cli.py` | new — shared helpers and the extend/shorten base |
| `src/django_countdown/utils.py` | new — `format_duration` |
| `src/django_countdown/models.py` | `time_remaining()` delegates to `format_duration` |
| `src/django_countdown/management/commands/start_countdown.py` | use `_cli`; success message points at `stop_countdown` instead of admin/shell |
| `tests/test_stop_countdown.py` | new |
| `tests/test_extend_shorten_countdown.py` | new |
| `tests/test_show_countdown.py` | new |
| `CHANGELOG.md` | new entry |

## Testing

New test files follow the conventions in `tests/test_start_countdown.py`
(`call_command`, `StringIO`, `pytest.mark.django_db`), with `pytest-mock` for
patching `is_interactive` / `ask`.

**`stop_countdown`**

1. No countdowns at all, no `--noinput` — succeeds rather than raising, because
   the empty check precedes the TTY check.
2. One countdown, no arguments — removed.
3. Countdowns on several sites, no arguments — all removed.
4. `--site-id` — removes only that site's countdown; the others survive.
5. `--site-id` naming a `Site` that does not exist — `CommandError`.
6. `--site-id` naming a real `Site` that has no countdown — no-op, and other
   sites' countdowns survive. This is what proves `--site-id` does not silently
   fall back to the all-sites path.
7. A countdown exists, not a TTY, no `--noinput` — `CommandError`, row survives.
8. Interactive confirmation accepted, and refused — refusal leaves the row.
9. Output names the removed domains.
10. Integration: middleware returns 503, `stop_countdown` runs, middleware returns
    200 for the same request.

**`extend_countdown` / `shorten_countdown`**

11. `extend --service` on a running (expired, blocked) countdown — the case
    `full_clean()` would reject. Confirms the window moves and the row saves.
12. `extend --banner` slides both boundaries and preserves the window length.
13. `shorten --banner` slides both boundaries the other way.
14. `extend --banner` on an expired countdown — `CommandError`.
15. `shorten --banner` past now — `CommandError`, row unchanged.
16. `--service` on an indefinite countdown — `CommandError` for both commands.
17. `shorten --service` landing at or before `countdown_time` — `CommandError`.
18. Neither `--banner` nor `--service`, and both together — `CommandError`.
19. Multi-site where one row violates a guard — nothing is written to any row.
20. `updated_at` actually advances (guards against omitting it from
    `update_fields`).
21. Integration: blocked site, `extend --service`, still blocked; then time
    passes beyond the new end, unblocked.

**`show_countdown`**

22. Each of the five phases reports the right phase and next transition.
23. No countdowns — one line, exit `0`.
24. Blocked site still exits `0`.
25. `--json` is parseable and carries `phase`, `next_event`, `seconds_to_next`,
    with `null` for the phases that have no next transition.
26. `--site-id` limits the report.
27. The reported phase agrees with what the middleware does for the same row —
    parametrised over the phases, so the report cannot drift from behaviour.

## Out of scope for this branch

`docs/`, `mkdocs.yml` and `README.md` are being rewritten concurrently on another
branch and are not present in this worktree. Documentation lands as a follow-up
once that work is merged:

- `docs/guide/management-command.md` — retitle to the plural, document all four
  new commands.
- `docs/guide/multisite.md:72-108` — currently states "There is no 'all sites'
  mode" and gives a `manage.py shell` one-liner for reopening every site. Both
  are superseded by `stop_countdown`.
- `mkdocs.yml` nav, and the README command section.

Making `SiteCountdown` a singleton is also out of scope. Dropping the `Site`
foreign key would simplify the middleware and the context processor, but it is a
breaking change to a published package (0.2.1): it needs a destructive migration
and a rewrite of `middleware.py:42-50`, `context_processors.py:17-18`, `admin.py`
and the templates. It also removes a capability that `django.contrib.sites`
exists to provide — one Django serving several domains, where maintenance affects
only one of them. If the singleton is still wanted, it is its own decision for
0.3 or 1.0, with a migration and a breaking-change note, not a rider on these
commands.

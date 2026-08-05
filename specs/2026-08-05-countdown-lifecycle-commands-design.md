# Countdown lifecycle commands — design

**Date:** 2026-08-05
**Status:** draft, revised after review
**Branch:** `worktree-stop-countdown` (rebased onto `38db43b`)

## Problem

`django-countdown` ships exactly one management command, `start_countdown`. It
can create a countdown and nothing else. There is no scriptable way to remove
one, to adjust one that is already running, or even to ask what the current state
is.

The package admits the first gap in its own success message
(`start_countdown.py:368-370`), and the documentation states it outright
(`docs/guide/management-command.md:152`):

> There is no `stop_countdown`. Deleting the row is the unblock action.

The docs then hand the reader a `manage.py shell -c` one-liner, both there and in
`docs/guide/multisite.md:101-108`, and build a deploy script around it
(`docs/guide/management-command.md:178-181`).

That is the wrong shape for the situations these actions serve. Every one of them
happens under time pressure — the site is closing, or already closed, and the
window is not going to plan. They should be single commands, safe to put in a
runbook, not shell one-liners composed while the site is down.

## The command set

| Command | Status | Purpose |
|---|---|---|
| `start_countdown` | exists | Create or replace a countdown. |
| `stop_countdown` | new | Delete countdowns. Reopen the site. |
| `extend_countdown` | new | Push a boundary later, or hold a floor under it. |
| `shorten_countdown` | new | Pull a boundary earlier. |
| `show_countdown` | new | Report the current phase and time to the next transition. |

All five follow `<verb>_countdown`, so they group together in `manage.py help`
under `[django_countdown]` and read as a family.

### Why not one `adjust_countdown` with a signed duration

`extend` and `shorten` are the same operation with opposite signs, so one command
taking `+15m` / `-15m` is tempting. Two commands are better here for two reasons.

`parse_relative` currently rejects negative input — `-5m` is in the
rejected-input list at `tests/test_start_countdown.py:38`. Supporting signed
durations means loosening a regex that `start_countdown` also depends on, for no
gain.

More importantly, these commands run during an incident. `shorten_countdown
+15m` cannot be misread; `adjust_countdown -15m` can, and the failure mode of a
sign error is closing the site fifteen minutes early instead of late.

The two commands share an implementation (see *Shared helpers*), so the
duplication is in the CLI surface only, which is exactly where the redundancy is
worth paying for.

`shorten_countdown` is the weakest member of the set — reopening *now* is
`stop_countdown`, and closing earlier than announced is rare and unkind to
visitors. It is included because it was asked for, and because it costs one sign
flip on a shared base class. It is not free, though: it roughly doubles the guard
and test surface.

---

## Shared conventions

### Scope

| Command | Default target | Widening |
|---|---|---|
| `show_countdown` | every countdown | — |
| `stop_countdown` | every countdown | — |
| `extend_countdown` | the current site | `--all` |
| `shorten_countdown` | the current site | `--all` |

All four accept `--site-id N` to name one site explicitly. `--site-id` and
`--all` are mutually exclusive.

**Why `stop` and `show` default to everything.** They are incident tools. They run
when something is wrong, and must not require the operator to first work out
which `SITE_ID` is to blame. A per-site default invites the failure where the
countdown is cleared for `SITE_ID=1` while a row attached to a different `Site` —
often the `example.com` row that `migrate` creates and nobody edits — keeps
traffic blocked. `show` is read-only, so a wide default costs nothing at all.

**Why `extend` and `shorten` do not.** They edit a schedule rather than ending
one, so the blast radius of a wrong target is a *different tenant's* maintenance
window silently moving. Worse, a wide default would fight the all-or-nothing rule
below: a single unschedulable row anywhere — indefinite, unscheduled, already
finished — would abort the whole run. On exactly the multi-site installations a
wide default is meant to serve, the operator would be forced back to `--site-id`
anyway. The default buys nothing and adds a footgun, so these two match
`start_countdown` and target the current site.

If `--site-id` names a `Site` that does not exist, the command raises
`CommandError`. A typo in the id must not be reported as "nothing to do". This
mirrors `start_countdown._resolve_site` (`start_countdown.py:210-215`).

### Empty target

| Command | Nothing to act on |
|---|---|
| `show_countdown` | prints a notice, exits `0` |
| `stop_countdown` | prints a notice, exits `0` |
| `extend_countdown` | `CommandError` |
| `shorten_countdown` | `CommandError` |

`stop_countdown` is genuinely idempotent — deleting nothing twice is deleting
nothing — so a no-op keeps it safe in a deploy script without `|| true`.

`extend`/`shorten` are **not** idempotent in their `--banner`/`--service` modes:
a retried step extends twice. Since a retry is already unsafe there, silently
succeeding when there is nothing to extend would only hide a second kind of
mistake. They fail loudly instead, which also makes them consistent with their own
`countdown_time is None` guard — "no row" and "row with nothing scheduled" mean
the same thing to an operator and must not exit differently.

The `--at-least` mode *is* idempotent; see its section for the heartbeat idiom
that relies on it.

For `stop` and `show`, the empty check runs **before** the TTY check, so a
non-TTY run with nothing to do is a clean no-op rather than an error. There is
nothing to confirm, so refusing to proceed would be noise.

### Confirmation

The three mutating commands print what they are about to change, then ask for
confirmation, defaulting to **no**. `--noinput` / `--no-input` skips the prompt.
If stdin is not a TTY and `--noinput` was not passed, they raise `CommandError`
naming `--noinput` as the fix.

This is the same mechanism as `start_countdown.py:251-254`, but not the same
message: that one tells the operator to pass `--banner`, because there the
missing input is a value rather than a permission.

The default answer also differs. `start_countdown`'s final confirmation defaults
to yes (`start_countdown.py:337`, `Apply? [Y/n]`); its destructive prompt defaults
to no (`:315`, `Replace it? [y/N]`). The new commands are all destructive or
schedule-altering, so they follow the second precedent uniformly.

### All-or-nothing, and the confirmation race

When a command targets several sites and any one fails a guard, nothing is
written. Guards are evaluated for every target first and the whole run aborts with
`CommandError` naming the offending sites. A partially applied schedule change is
worse than a refused one.

The guards depend on `now`, and an interactive confirmation can sit open for
minutes. Sampling `now` once, before the prompt, would reintroduce exactly the
states the guards exist to forbid:

- `shorten --banner` computed to land 40 seconds in the future passes the guard;
  the operator confirms two minutes later; the saved `countdown_time` is now in
  the past, violating the `models.py:80-88` invariant and closing the site earlier
  than the preview promised.
- `extend --banner` passes the not-yet-expired guard during the banner phase; the
  countdown expires while the prompt is open; the save slides `countdown_time`
  back into the future, reopening the site and replaying the banner — the exact
  scenario that guard exists to forbid.

So the write path is:

```python
with transaction.atomic():
    rows = queryset.select_for_update()   # re-read after the prompt
    # re-run every guard against a fresh timezone.now()
    # abort with CommandError if the state changed while waiting
    # then save each row
```

The preview shown before the prompt is computed from the first read; the values
actually written are recomputed from the re-read rows. If a guard that passed now
fails, the command aborts and says the state changed rather than writing a stale
plan. `select_for_update` also closes the window where a concurrent admin edit
would be clobbered by `save(update_fields=...)`.

### Exit statuses

`0` for success, no-op and user abort. `CommandError` (Django exits `1`) for an
unknown `--site-id`, for a non-TTY run without `--noinput`, for an empty target on
`extend`/`shorten`, and for the per-command guard violations below.

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

1. Resolve the target queryset.
2. If empty, print a notice and return.
3. List what will go: one line per countdown with site domain, message,
   `countdown_time`, and current phase.
4. Confirm unless `--noinput`. Any answer other than `y`/`yes` prints `Aborted.`
   and returns without deleting.
5. A single queryset `DELETE`, inside `transaction.atomic()`.
6. Report `✓ Removed N countdown(s).` and the affected domains.

---

## `extend_countdown` and `shorten_countdown`

```console
$ ./manage.py extend_countdown  (--banner +15m | --service +20m | --at-least 5m) [--site-id N | --all] [--noinput]
$ ./manage.py shorten_countdown (--banner +15m | --service +20m)                 [--site-id N | --all] [--noinput]
```

Durations use the existing `+<N>[s|m|h|d]` syntax and the existing
`parse_relative`, and are always **positive**. Exactly one mode flag is required;
passing several or none is a `CommandError`. Allowing `--banner` and `--service`
together would raise the question of whether the banner shift also drags the
service edge, and there is no answer that is obvious to a reader.

`--at-least` belongs to `extend_countdown` only. Its inverse — "make sure the
window is *no more* than N from now" — is a scheduled shutdown, not a shortening,
and nobody has asked for it.

### Which edge: `--banner` vs `--service`

"Extend the countdown" is ambiguous, because the model has two time boundaries,
and both are genuinely extended in practice — just in different situations. The
flags reuse `start_countdown`'s vocabulary and mean the same thing they mean
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
| `extend` | `--at-least` | unchanged | `max(current, now + D)` |
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

### `--at-least`: the idempotent mode

`extend_countdown --at-least 5m` guarantees that the window ends **no sooner than
five minutes from now**. It does not add anything. If `maintenance_until` is
already further out, the command reports "already covered" and writes nothing.

Two properties follow, and both matter:

**It is idempotent.** Run ten times, it leaves the same state as running once.
`--service` cannot say that: a retried deploy step extends the window twice.
`--at-least` is therefore the only mode that belongs in a retry loop or a cron
job.

**It is measured from now, not from `countdown_time`.** That is what makes it a
different mode rather than a modifier. A heartbeat has no idea when the window was
scheduled to start; it only knows it is still working.

Which gives the dead man's switch:

```bash
# while the deploy runs, keep the window five minutes ahead of the present
while deploy_is_running; do
    ./manage.py extend_countdown --at-least 5m --noinput || true
    sleep 60
done
```

If the deploy finishes, `stop_countdown` reopens the site. If the deploy *dies*,
nothing renews the floor, the window expires five minutes later and the site
reopens by itself. That is strictly better than the current documented advice
(`docs/guide/management-command.md:184-186`), which recommends `--service
indefinite` plus an explicit delete at the end — safe when the deploy succeeds,
and a permanently closed site when it does not.

The `|| true` is deliberate and documented: if an operator has already run
`stop_countdown`, there is no row, the command exits non-zero per the empty-target
rule, and the heartbeat must not resurrect anything.

`--at-least` against an **indefinite** window is a silent success, not an error.
"Never ends" satisfies "ends no sooner than five minutes from now", so there is
nothing to do. This is the one place `--at-least` and `--service` deliberately
diverge, and it exists so a heartbeat does not fall over on an indefinite window.

### Guards

Each raises `CommandError` naming the command that *does* fit the intent:

| Condition | Applies to | Reason |
|---|---|---|
| `countdown_time is None` | all modes | Nothing is scheduled. Use `start_countdown`. |
| `--banner` on an already-expired countdown | `extend`, `shorten` | The banner phase is over; the site is closed. Sliding it would reopen the site and replay the banner. Use `start_countdown --force` to reschedule, or `stop_countdown` to reopen now. |
| `shorten --banner` landing at or before now | `shorten` | `countdown_time` must stay in the future — the invariant at `models.py:80-88`. |
| `maintenance_until is None` | `--service` only | The window is indefinite; it has no end to move. Use `start_countdown --force` to give it one, or `stop_countdown` to reopen now. (`--at-least` succeeds silently here instead.) |
| Window already finished (`now >= maintenance_until`) | `--service`, `--at-least` | The site has **already reopened**. Extending would close a site that visitors are currently using — a state transition, not a nudge. Use `start_countdown --force` to schedule a new window. |
| `shorten --service` landing at or before now | `shorten` | Reopening immediately is `stop_countdown`. Landing between `countdown_time` and now would reopen the site *and* leave a stale row that forces `--force` on the next `start_countdown` (`start_countdown.py:299-305`) — the clutter `stop_countdown` exists to avoid. |

The finished-window guard is the reason `extend_countdown --at-least` cannot
re-close a site behind the operator's back: a stale heartbeat firing after the
window has ended gets an error, not a resurrection.

### Persistence: why not `full_clean()`

`SiteCountdown.clean()` (`models.py:80-88`) rejects **any** `countdown_time` in
the past. Once a countdown has expired — which is to say, whenever the site is
actually down — the object can no longer pass `full_clean()` at all, no matter
what is being changed.

That is precisely the state in which `extend_countdown --service` is most likely
to be run. So these commands must not call `full_clean()`. They validate
explicitly via the guards above, which reproduce both invariants `clean()`
enforces, and then persist with:

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

1. Resolve the target queryset. If empty, `CommandError`.
2. Compute new values and evaluate all guards; any violation aborts the run.
3. Show a before → after line per site. `--at-least` targets already covered are
   listed as unchanged.
4. Confirm unless `--noinput`.
5. Inside `transaction.atomic()`, re-read with `select_for_update()`, recompute
   against a fresh `now`, re-run the guards, then save with `update_fields`.
6. Report the new schedule.

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

If a Nagios-style exit code is ever wanted, it should arrive as an explicit
`--fail-when=blocked` rather than as a change to the default.

### Phases

Evaluated **top to bottom; the first match wins.** The order is load-bearing:
`clean()` only compares `maintenance_until` against `countdown_time`, and only
when both are set (`models.py:89-90`), so a row with `countdown_time = None` and a
past `maintenance_until` is reachable through the admin and matches more than one
condition below.

| # | Phase | Condition | Next transition |
|---|---|---|---|
| 1 | `unscheduled` | `countdown_time is None` | none |
| 2 | `banner` | `now < countdown_time` | site closes at `countdown_time` |
| 3 | `blocked_indefinite` | `maintenance_until is None` | none — needs `stop_countdown` |
| 4 | `finished` | `now >= maintenance_until` | none — row is stale |
| 5 | `blocked` | otherwise | site reopens at `maintenance_until` |

Rows 2-5 all assume `countdown_time is not None`, which row 1 has already
guaranteed.

These are the same conditions the middleware branches on
(`middleware.py:52-61`), so the report tracks real behaviour rather than a
parallel guess at it. It describes what an **anonymous visitor to a normal path**
gets: the middleware also exempts `/admin/`, `/static/` and `/media/`
(`middleware.py:33-39`) and lets superusers through (`:56-61`), so a superuser
browsing happily while `show_countdown` says `blocked` is correct on both sides.

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

A JSON array on stdout, one object per countdown, using the machine-readable
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
monitoring check or a deploy gate can consume. An empty result is `[]`, not a
prose line, so a consumer never has to special-case it.

---

## Refactor: shared helpers

### `management/commands/_cli.py` (new)

`start_countdown.py` keeps four helpers the new commands also need:
`format_when` (module-level), and `_interactive`, `_ask`, `_resolve_site`
(methods on `Command` that never touch `self`).

Move all four there as module functions `format_when`, `is_interactive`, `ask`,
`resolve_site`, and update `start_countdown` to call them.

Django's `find_commands()` filters out module names starting with `_`
(`django/core/management/__init__.py`, `not name.startswith("_")`), so `_cli` will
not appear in `manage.py help`.

The module also carries what the four new commands share: target resolution from
`--site-id`/`--all`, the empty-target rule, the TTY check, the confirmation
prompt, the atomic re-read-and-reguard write path, and phase classification.
`extend_countdown` and `shorten_countdown` are the same command with an opposite
sign, so they are built on a common base class parameterised by that sign; each
concrete command supplies only its name, help text, direction, and whether it
offers `--at-least`.

This does not break the existing tests: `tests/test_start_countdown.py:11-15`
imports only `parse_relative`, `parse_service` and `INDEFINITE_TOKENS`, all of
which stay in `start_countdown.py`, and no other test module imports from it.

### `django_countdown/utils.py` (new)

`SiteCountdown.time_remaining()` (`models.py:99-121`) formats a duration as
`"2 days 3 h 5 min"`, but only ever for `countdown_time`. `show_countdown` needs
the same formatting for the maintenance side too.

Extract the formatting into `format_duration(seconds)` in a package-level
`utils.py` and have `time_remaining()` delegate to it. It lives at package level,
not under `management/`, because the model must not import from the command
layer.

The existing `gettext` msgids (`"%(n)d days"`, `"%(n)d h"`, `"%(n)d min"`,
`"%(n)d sec"`) move unchanged, so the compiled catalogues stay valid — `.po` files
carry source line numbers as comments only.

## Files

| File | Change |
|---|---|
| `src/django_countdown/management/commands/stop_countdown.py` | new |
| `src/django_countdown/management/commands/extend_countdown.py` | new |
| `src/django_countdown/management/commands/shorten_countdown.py` | new |
| `src/django_countdown/management/commands/show_countdown.py` | new |
| `src/django_countdown/management/commands/_cli.py` | new — shared helpers, target resolution, atomic write path, extend/shorten base |
| `src/django_countdown/utils.py` | new — `format_duration` |
| `src/django_countdown/models.py` | `time_remaining()` delegates to `format_duration` |
| `src/django_countdown/management/commands/start_countdown.py` | use `_cli`; success message points at `stop_countdown` instead of admin/shell |
| `tests/test_stop_countdown.py` | new |
| `tests/test_extend_shorten_countdown.py` | new |
| `tests/test_show_countdown.py` | new |
| `docs/guide/management-command.md` | retitle; replace §"Clearing a countdown" and the deploy recipe |
| `docs/guide/managing-a-countdown.md` | new page for the four new commands |
| `docs/guide/multisite.md` | replace the "no all-sites mode" and shell-reopen sections |
| `docs/index.md`, `docs/getting-started/quickstart.md` | mention the new commands where `start_countdown` is introduced |
| `mkdocs.yml` | nav entry for the new page |
| `README.md` | command list |
| `CHANGELOG.md` | new entry |

## Documentation

The docs site landed on `main` in `38db43b` and is now in scope.

**`docs/guide/management-command.md`** (186 lines) stays the `start_countdown`
deep-dive, renamed in the nav to *Scheduling a countdown*; the filename is kept so
existing links survive. Two sections are wrong as of this branch:

- `:150-162` §"Clearing a countdown" opens with "There is no `stop_countdown`"
  and gives a `manage.py shell` one-liner. Replaced by a pointer to the new page.
- `:164-186` §"Automating around the window" builds a deploy script on
  `--service indefinite` plus a shell delete, and argues it is safer than a fixed
  window. That argument survives only because there was no other option; the
  `--at-least` heartbeat is safer than both. Rewritten.

**`docs/guide/managing-a-countdown.md`** (new) covers `show`, `stop`, `extend`,
`shorten`, in that order — the order an operator meets them. Target length is
150-200 lines, matching the rest of `guide/`. Putting five commands on one page
would push it past 400.

**`docs/guide/multisite.md`** — `:74` states "There is no 'all sites' mode" and
`:101-108` gives the shell one-liner for reopening everything. Both are superseded
by `stop_countdown`. The page also needs the new scope split: `stop`/`show` are
site-wide by default, `extend`/`shorten` are not.

## Testing

New test files follow the conventions in `tests/test_start_countdown.py`
(`call_command`, `StringIO`, `pytest.mark.django_db`), with `pytest-mock` for
patching `is_interactive` / `ask`.

**Time control.** There is no `freezegun` or `time-machine` in the test extras
(`pyproject.toml:37-42`), and none is added. Past-state rows are constructed
directly with `objects.create()`, which never calls `clean()` and so accepts
timestamps the admin would reject. Where a test needs time to *pass*, it patches
`django.utils.timezone.now` via `mocker`: every module reaches it through the
`timezone` module attribute rather than a `from … import now`, so one patch covers
the model, the middleware and the commands at once.

**`stop_countdown`**

1. No countdowns at all, no `--noinput` — succeeds rather than raising, because
   the empty check precedes the TTY check.
2. One countdown, no arguments — removed.
3. Countdowns on several sites, no arguments — all removed.
4. `--site-id` — removes only that site's countdown; the others survive.
5. `--site-id` naming a `Site` that does not exist — `CommandError`.
6. `--site-id` naming a real `Site` with no countdown — no-op, other sites'
   countdowns survive. Proves `--site-id` does not fall back to the all-sites path.
7. A countdown exists, not a TTY, no `--noinput` — `CommandError`, row survives.
8. Interactive confirmation accepted, and refused — refusal leaves the row.
9. Output names the removed domains.
10. Integration: middleware returns 503, `stop_countdown` runs, middleware returns
    200 for the same request.

**`extend_countdown` / `shorten_countdown`**

11. `extend --service` on a running (expired, blocked) countdown — the case
    `full_clean()` would reject. The window moves and the row saves.
12. `extend --banner` slides both boundaries and preserves window length.
13. `shorten --banner` slides both boundaries the other way.
14. `extend --banner` on an expired countdown — `CommandError`.
15. `shorten --banner` past now — `CommandError`, row unchanged.
16. `--service` on an indefinite countdown — `CommandError` for both commands.
17. `shorten --service` landing at or before now — `CommandError`.
18. `--service` and `--at-least` on a finished window — `CommandError`; the row is
    not resurrected and the site stays open.
19. No mode flag, and two mode flags together — `CommandError`.
20. `--at-least` when the window already extends further — no write, and
    `updated_at` does not move.
21. `--at-least` when the window ends sooner — `maintenance_until` becomes
    `now + D`, and `countdown_time` is untouched.
22. `--at-least` twice in a row leaves the same state as once, modulo clock
    advance — the idempotence claim.
23. `--at-least` on an indefinite window — exits `0`, writes nothing.
24. `--at-least` on a site with no countdown — `CommandError` (the `|| true` case
    from the heartbeat recipe).
25. Default scope is the current site: with countdowns on two sites and no flags,
    only the current site's row moves.
26. `--all` moves every site's row; `--site-id` and `--all` together —
    `CommandError`.
27. `--all` where one row violates a guard — nothing is written to any row.
28. `updated_at` advances on a real change (guards against omitting it from
    `update_fields`).
29. Unparseable and negative durations (`--service nope`, `--service -5m`) —
    `CommandError`.
30. `extend --banner` on an indefinite countdown in the banner phase — exercises
    the `+= D (if set)` branch with `maintenance_until is None`.
31. Confirmation refused — rows unchanged.
32. Unknown `--site-id` — `CommandError`.
33. The confirmation race: guards pass, `now` advances past the boundary while the
    prompt is open, the re-check fails and nothing is written.
34. Integration: blocked site, `extend --service`, still blocked; time advances
    past the new end, unblocked.

**`show_countdown`**

35. Each of the five phases reports the right phase and next transition.
36. A row with `countdown_time = None` and a past `maintenance_until` reports
    `unscheduled`, not `finished` — the phase-ordering case.
37. No countdowns — one line for humans, `[]` for `--json`, exit `0`.
38. A blocked site still exits `0`.
39. `--json` parses and carries `phase`, `next_event`, `seconds_to_next`, with
    `null` for phases that have no next transition.
40. `--site-id` limits the report, and combines with `--json`.
41. The reported phase agrees with what the middleware does for the same row,
    parametrised over the phases, so the report cannot drift from behaviour.

## Build order

Three commits, each green on its own:

1. **Pure refactor** — `_cli.py`, `utils.py`, `start_countdown` rewired. No
   behaviour change; the existing 52 tests stay green and are the proof.
2. **`stop_countdown` + `show_countdown`** — the read-only one and the simple
   destructive one. This alone closes the gap the package opens with: the
   indefinite-mode dead end.
3. **`extend_countdown` + `shorten_countdown`** — the guard-heavy half.

Documentation follows each step rather than landing in a lump at the end.

## Out of scope

Making `SiteCountdown` a singleton. Dropping the `Site` foreign key would simplify
the middleware and the context processor, but it is a breaking change to a
published package (0.2.1): it needs a destructive migration and a rewrite of
`middleware.py:42-50`, `context_processors.py:17-18`, `admin.py` and the
templates. It also removes a capability that `django.contrib.sites` exists to
provide — one Django serving several domains, where maintenance affects only one
of them. If the singleton is still wanted, it is its own decision for 0.3 or 1.0,
with a migration and a breaking-change note, not a rider on these commands.

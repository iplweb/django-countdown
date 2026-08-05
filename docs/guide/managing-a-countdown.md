# Managing a running countdown

[`start_countdown`](management-command.md) schedules a window. These four
commands are for everything after that: seeing where a window stands, moving its
boundaries when the plan slips, and ending it.

```console
$ ./manage.py show_countdown      # where does it stand?
$ ./manage.py extend_countdown    # it is taking longer
$ ./manage.py shorten_countdown   # it is going faster
$ ./manage.py stop_countdown      # done — reopen the site
```

They exist because the alternative was a `manage.py shell` one-liner composed
while the site was down. That is the wrong tool for a moment when nothing else is
going right.

## The two boundaries

Every command below acts on one of two moments, and uses the same words
`start_countdown` does:

```
    now              countdown_time            maintenance_until
     │◄─── --banner ────►│◄────── --service ──────►│
     │                   │                         │
  announced          site closes              site reopens
```

`--banner` moves **when the site closes**. `--service` moves **when it reopens**.

## Where does it stand — `show_countdown`

Read-only. It never prompts, never writes, and always exits `0` — including when
the site is blocked, because being blocked is a normal state for this package and
not a failure of the command. Read the output, not the exit status.

```console
$ ./manage.py show_countdown
example.com — Wielka migracja
  phase   banner showing
  next    site closes 2026-08-05 03:08:17 CDT (in 9 min 59 sec)
  then    site reopens 2026-08-05 03:38:17 CDT (30 min window)
```

Once the window is running:

```console
$ ./manage.py show_countdown
example.com — Trwa migracja
  phase   blocked — maintenance running
  next    site reopens 2026-08-05 03:23:34 CDT (in 24 min 59 sec)
```

And the state that needs a human:

```console
$ ./manage.py show_countdown
example.com — Trwa migracja
  phase   blocked — indefinite maintenance
  since   site closed 2026-08-05 02:53:34 CDT
  next    never — run stop_countdown to reopen
```

### The five phases

| Phase | Meaning | What happens next |
|---|---|---|
| `unscheduled` | A row exists with no `countdown_time` | Nothing |
| `banner` | Announced, not yet closed | The site closes at `countdown_time` |
| `blocked` | Closed, inside the window | The site reopens at `maintenance_until` |
| `blocked_indefinite` | Closed, no end set | Nothing — needs `stop_countdown` |
| `finished` | The window is over | Nothing — the row is stale |

These are the same conditions the middleware branches on, so the report describes
what visitors actually get.

!!! note "…what *anonymous* visitors get"

    The middleware exempts `/admin/`, `/static/` and `/media/`, and lets
    superusers through. A superuser browsing happily while `show_countdown`
    reports `blocked` is both things working correctly.

### `--json` for monitoring

```console
$ ./manage.py show_countdown --json
[{"site_id": 1, "domain": "example.com", "message": "Wielka migracja",
  "phase": "banner", "countdown_time": "2026-08-05T03:08:17-05:00",
  "maintenance_until": "2026-08-05T03:38:17-05:00",
  "next_event": "site_closes", "seconds_to_next": 599}]
```

`next_event` is `site_closes`, `site_reopens` or `null`; `seconds_to_next` is
`null` for the phases nothing will move on. With no countdowns the output is
`[]`, never prose, so a consumer never has to special-case emptiness.

This is the reason a status command exists at all rather than just an admin page:
it is the piece a monitoring check or a deploy gate can consume.

## Reopening — `stop_countdown`

Deletes the row, which is the unblock action. In indefinite mode it is the *only*
way back.

```console
$ ./manage.py stop_countdown
About to remove 1 countdown(s):
  example.com  [blocked — indefinite maintenance]  2026-08-05 02:53:34 CDT  — Trwa migracja

Remove 1 countdown(s)? [y/N]: y

✓ Removed 1 countdown(s).
  example.com — unblocked
```

Deleting rather than merely ending the window leaves a clean slate: a surviving
row would still count as "an existing countdown" and force `--force` on the next
`start_countdown`, and it would clutter the admin with rows that no longer mean
anything.

!!! warning "It sweeps every site by default"

    `stop_countdown` with no arguments removes **every** countdown, not just the
    current site's. That is deliberate — it runs when the site is down and you
    should not have to work out which `SITE_ID` is to blame first, especially
    since the culprit is often the `example.com` row that `migrate` creates and
    nobody edits.

    On a multi-tenant install, pass `--site-id` so you do not take out a
    neighbour's scheduled window.

Nothing to delete is a success, not an error, so it is safe in a deploy script
without `|| true`.

## Moving a boundary — `extend_countdown` and `shorten_countdown`

Both take a **positive** duration in the usual `+15m` / `+2h` / `+1d` syntax, and
exactly one mode flag.

| Command | Flag | Effect |
|---|---|---|
| `extend_countdown` | `--banner +15m` | The whole schedule slides 15 min later; the window keeps its length |
| `extend_countdown` | `--service +20m` | The site reopens 20 min later than planned |
| `extend_countdown` | `--at-least 5m` | Guarantees the window ends no sooner than 5 min from **now** |
| `shorten_countdown` | `--banner +15m` | The whole schedule slides 15 min earlier |
| `shorten_countdown` | `--service +20m` | The site reopens 20 min sooner |

The one you will reach for while already down is `--service`:

```console
$ ./manage.py extend_countdown --service +20m
example.com  blocked — maintenance running
  reopens  2026-08-05 03:45:13 CDT → 2026-08-05 04:05:13 CDT

Apply to 1 countdown(s)? [y/N]: y

✓ Extended 1 countdown(s).
  example.com — reopens 2026-08-05 04:05:13 CDT
```

Every run previews `before → after` and asks before writing. `--noinput` skips
the question; without a terminal and without that flag the command refuses rather
than guessing.

!!! info "Why two commands instead of one signed duration"

    `shorten_countdown +15m` cannot be misread. `adjust_countdown -15m` can, and
    the cost of a sign error here is closing the site fifteen minutes early
    instead of late.

### These two default to the current site

The opposite of `stop_countdown` and `show_countdown`. They edit a schedule
rather than ending one, so a wrong target silently moves *another tenant's*
maintenance window. Pass `--all` to widen deliberately.

### Absolute times are `start_countdown`'s job

There is no `--banner 2026-08-05T14:00`. Setting a boundary to a specific moment
is `start_countdown --force`, which validates the whole schedule.
`extend`/`shorten` exist for relative nudges to a window already in flight.

## `--at-least`: the mode built for loops

`extend_countdown --at-least 5m` does not add anything. It guarantees the window
ends **no sooner than five minutes from now**, and writes nothing if it already
does.

Repeated runs absorb rather than accumulate: a run at `t₀` followed by one at
`t₁` leaves the same state as a single run at `t₁`, so a retry can never
overshoot. `--service` cannot say that — a retried step there moves the boundary
twice.

That makes it the one mode that belongs in an unattended loop:

```bash title="deploy.sh"
./manage.py start_countdown --banner +10m --service +15m \
    --message "Deploying" --noinput --force

while deploy_is_running; do
    ./manage.py extend_countdown --at-least 5m --site-id "$SITE" --noinput \
        || alert "countdown protection lapsed"
    sleep 60
done

./manage.py stop_countdown --site-id "$SITE" --noinput
```

If the deploy finishes, `stop_countdown` reopens the site. If the deploy **dies**,
nothing renews the floor, the window expires five minutes later, and the site
reopens by itself.

!!! danger "Do not wrap it in `|| true`"

    An empty target is deliberately a *success* for `--at-least`, precisely so
    this loop needs no `|| true`. With it, "the row is gone because someone ran
    `stop_countdown`" and "the floor lapsed and the site is already serving
    traffic mid-deploy" both become silence — and the second one is worth waking
    someone for.

Against an indefinite window `--at-least` writes nothing and warns:

```console
$ ./manage.py extend_countdown --at-least 5m --noinput
example.com  banner showing
  unchanged  the window is indefinite
  ⚠  this window never expires, so nothing is being held: the site will not reopen on its own. Run stop_countdown when the work is done.

✓ Nothing to change.
```

"Never ends" does satisfy "ends no sooner than five minutes from now", so this is
a success rather than an error. But the guarantee you wanted is absent — a dead
man's switch cannot fire against a window that never expires — and silence here
would read as protection.

## Which deploy pattern

The heartbeat is not simply better than an indefinite window. They fail in
opposite directions:

| | The deploy process dies | The heartbeat's own host dies mid-migration |
|---|---|---|
| `--service indefinite` + explicit `stop_countdown` | Site stays closed until someone notices | Site stays closed — safe |
| `--at-least` heartbeat | Site reopens by itself after `D` — safe | Site reopens onto a half-migrated database |

The second column deserves thought, because the heartbeat host is very often *the
machine being deployed*: half-installed dependencies can take `extend_countdown`
down along with everything else.

Use the heartbeat when an early reopen is survivable and an unattended permanent
closure is not. Use the indefinite window when serving a half-migrated database
is the worse outcome.

!!! tip "Leave room in `D`"

    Clock skew between the heartbeat host and the database is subtracted from
    your margin. Pick `D` with slack rather than at the theoretical minimum.

## Errors these commands raise

| Message | Cause |
|---|---|
| `Site with id=N does not exist` | Bad `--site-id`. A typo is an error, never a quiet "nothing to do". |
| `--site-id and --all are mutually exclusive` | Pick one. |
| `no terminal attached … pass --noinput` | Run from CI or a pipe with a confirmation pending. |
| `nothing is scheduled` | The row has no `countdown_time`. Use `start_countdown`. |
| The banner phase is over | `--banner` on a countdown that already expired. Use `start_countdown --force` to reschedule, or `stop_countdown`. |
| The window is indefinite | `--service` has no end to move. `--at-least` warns instead of failing. |
| The site has already reopened | `--service`/`--at-least` on a finished window. Moving the end of a window that is over is a state transition, not a nudge. |

When a run targets several sites and any one of them fails a guard, **nothing is
written anywhere** — every offending site is named at once, so fixing them does
not take one run per problem.

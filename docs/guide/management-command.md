# Scheduling a countdown

`start_countdown` creates or replaces the countdown for one site. It is the
scriptable path into the package — the thing you put in a deploy hook, a
Makefile target or an on-call runbook.

Once a window exists, [Managing a running countdown](managing-a-countdown.md)
covers inspecting it, moving its boundaries, and ending it.

```console
$ ./manage.py start_countdown [options]
```

Interactive by default, fully non-interactive with `--noinput`.

## The mental model

Two durations, measured from different origins. This trips people up once:

```
    now                countdown_time              maintenance_until
     │◄──── --banner ────►│◄────── --service ──────►│
     │                    │                         │
  announced            site closes              site reopens
```

- `--banner` is measured **from now**.
- `--service` is measured **from `countdown_time`**, not from now.

So `--banner +15m --service +30m` means: warn for 15 minutes, then be down
for 30, total 45 minutes before the site is back.

## Options

| Option | Description |
|---|---|
| `--banner` | How long the banner shows before the site closes. A duration (`+15m`) or an absolute ISO datetime. Required with `--noinput`. |
| `--service` | How long the window lasts after the site closes. A duration (`+30m`) or `indefinite`. Required with `--noinput`. |
| `--message` | Banner headline, max 200 characters. Defaults to `Scheduled maintenance` under `--noinput`; prompted otherwise. |
| `--long-description` | Longer text shown on the maintenance page. Default empty. |
| `--site-id` | Which `Site` to attach to. Defaults to the current site (`SITE_ID`). |
| `--noinput`, `--no-input` | Never prompt. Fails rather than asking. |
| `--force` | Replace an existing countdown and skip the final confirmation. |

### Duration syntax

`+<number><unit>`, with the `+` optional and whitespace tolerated. **A bare
number means minutes**, so `--banner 5` and `--banner +5m` are the same thing.

| Unit | Accepted spellings |
|---|---|
| seconds | `s`, `sec`, `secs`, `second`, `seconds` |
| minutes | `m`, `min`, `mins`, `minute`, `minutes` — *the default* |
| hours | `h`, `hr`, `hrs`, `hour`, `hours` |
| days | `d`, `day`, `days` |

Indefinite mode accepts any of: `indefinite`, `indefinitely`, `forever`,
`inf`, `infinite`.

### Absolute datetimes

`--banner` also takes an ISO-8601 timestamp — `2026-08-05T22:00`,
`2026-08-05 22:00:00`. Naive values are interpreted in the current Django
timezone; aware values are used as-is.

!!! warning "`--service` does not accept ISO datetimes"

    Despite what `--help` says, `--service` is parsed as a duration or an
    indefinite token only. Passing a timestamp there fails with
    `can't parse … as a duration`. Express the window length instead:
    `--service +30m`.

## Recipes

=== "Deploy hook"

    ```console
    $ ./manage.py start_countdown \
          --banner +10m --service +20m \
          --message "Deploying release 4.2" \
          --long-description "New reporting module. Unsaved forms may be lost." \
          --noinput --force
    ```

=== "Emergency close, no end in sight"

    ```console
    $ ./manage.py start_countdown \
          --banner +1m --service indefinite \
          --message "Unplanned maintenance" --noinput --force
    ```

=== "Overnight window, absolute time"

    ```console
    $ ./manage.py start_countdown \
          --banner "2026-08-05 22:00" --service +2h \
          --message "Storage migration" --noinput
    ```

=== "Multi-tenant, one domain only"

    ```console
    $ ./manage.py start_countdown --site-id 3 \
          --banner +5m --service +15m \
          --message "Tenant migration" --noinput
    ```

=== "Interactive"

    ```console
    $ ./manage.py start_countdown
    How long should the banner show before the site is blocked?
      Suggestions: +5m, +30m, +1h, +1d  (or an ISO datetime)
    Banner duration [+5m]:

    How long should service mode last?
      Suggestions: +5m, +30m, +1h, +1d, or 'indefinitely'
    Service duration [+5m]:

    Short banner message [Scheduled maintenance]:
    ```

    Bad input is rejected and re-prompted rather than aborting.

## Confirmations and overwrites

There is exactly one countdown per site, so a second run replaces the first.
What happens depends on the flags:

| Situation | Interactive | `--noinput` | `--force` |
|---|---|---|---|
| No existing countdown | Shows a summary, asks `Apply? [Y/n]` | Applies silently | Applies silently |
| Countdown already exists | Shows the old values, asks `Replace it? [y/N]` | **Fails** — "Pass `--force` to replace it" | Replaces silently |

`--force` is what you want in automation that may run twice; `--noinput`
alone is the safer choice when a second run should be treated as a mistake.

## Errors you can hit

| Message | Cause |
|---|---|
| `--banner is required with --noinput` | Non-interactive run without an explicit banner duration |
| `--service is required with --noinput` | Same, for the window length |
| `stdin is not a TTY — pass --banner explicitly or use a TTY` | Run from CI or a pipe without `--banner`. Add `--noinput` and the durations. |
| `Banner end (…) must be in the future` | A zero or negative `--banner`, or an ISO timestamp already in the past |
| `Message must be at most 200 characters.` | `--message` too long for the model field |
| `A countdown already exists for …` | Non-interactive rerun without `--force` |
| `Site with id=N does not exist` | Bad `--site-id` |
| `No current Site — set SITE_ID and run 'migrate sites', or pass --site-id` | Sites framework not set up — see [Multi-site setup](multisite.md) |
| `Validation failed: {…}` | Model validation rejected the result; the row is deleted again, so nothing is left half-applied. `--service +0m` triggers this, because the window must be longer than zero. |

## Clearing a countdown

```console
$ ./manage.py stop_countdown --site-id 1
```

Deleting the row is the unblock action, and in indefinite mode it is the only
way back. The admin works too and stays reachable while the site is blocked. See
[Reopening](managing-a-countdown.md#reopening-stop_countdown) for the details —
including the fact that `stop_countdown` with no arguments sweeps every site.

## Automating around the window

A deploy script can bracket itself. The safest shape depends on which failure you
would rather have, and the choice is worth making deliberately:

```bash title="deploy.sh"
set -euo pipefail

./manage.py start_countdown --banner +10m --service +15m \
    --message "Deploying" --noinput --force --site-id "$SITE"
sleep 600                       # let the banner do its job

./deploy-the-thing.sh &
DEPLOY=$!

# hold the window open only while the deploy is actually alive
while kill -0 "$DEPLOY" 2>/dev/null; do
    ./manage.py extend_countdown --at-least 5m --site-id "$SITE" --noinput \
        || alert "countdown protection lapsed"
    sleep 60
done

./manage.py stop_countdown --site-id "$SITE" --noinput
```

`--at-least` is the mode to use in a loop: it raises a floor rather than adding
time, so a retry can never overshoot. If the deploy dies, nothing renews the
floor and the site reopens on its own five minutes later.

The older pattern — `--service indefinite` plus an explicit `stop_countdown` at
the end — trades the opposite way: nothing reopens the site until you say so, but
a deploy that dies silently leaves it closed indefinitely.

[Which deploy pattern](managing-a-countdown.md#which-deploy-pattern) lays the two
side by side. Neither is the default answer.

# Management command

`start_countdown` creates or replaces the countdown for one site. It is the
scriptable path into the package — the thing you put in a deploy hook, a
Makefile target or an on-call runbook.

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

There is no `stop_countdown`. Deleting the row is the unblock action:

```console
$ ./manage.py shell -c "
from django_countdown.models import SiteCountdown
SiteCountdown.objects.filter(site_id=1).delete()
"
```

Or delete it from the admin, which is reachable even while the site is
blocked. In indefinite mode this is the *only* way back.

## Automating around the window

Because the command is idempotent per site and takes relative durations, a
deploy script can bracket itself:

```bash title="deploy.sh"
set -euo pipefail

./manage.py start_countdown --banner +10m --service indefinite \
    --message "Deploying" --noinput --force
sleep 600                       # let the banner do its job

./deploy-the-thing.sh

./manage.py shell -c "
from django_countdown.models import SiteCountdown
SiteCountdown.objects.all().delete()
"
```

Indefinite mode plus an explicit delete at the end is safer than a fixed
`--service` window: if the deploy overruns, the site stays honestly closed
instead of reopening onto a half-migrated database.

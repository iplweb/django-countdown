# Contributing

Bug reports, translations and pull requests are welcome at
[iplweb/django-countdown](https://github.com/iplweb/django-countdown).

## Development setup

```console
$ git clone https://github.com/iplweb/django-countdown.git
$ cd django-countdown
$ uv sync --all-extras
$ uv run pytest
```

`--all-extras` pulls the `test`, `dev` and `docs` extras. The project uses
[uv](https://docs.astral.sh/uv/) throughout; every command below works the
same with an ordinary virtualenv and `pip install -e ".[test,dev,docs]"`.

## Layout

| Path | Contents |
|---|---|
| `src/django_countdown/` | The package |
| `tests/` | pytest suite with its own `tests/settings.py` |
| `example/` | Runnable demo project |
| `docs/` | This documentation |
| `mkdocs.yml` | Docs site configuration |

## Tests

```console
$ uv run pytest              # whole suite
$ uv run pytest -v -k banner # one slice
```

Four modules cover the model and middleware (`test_django_countdown.py`), the
admin (`test_admin.py`), the management command (`test_start_countdown.py`)
and the app config (`test_apps.py`) — 52 tests in about a second. They run
against in-memory SQLite with `tests/settings.py`, configured through
`[tool.pytest.ini_options]` in `pyproject.toml` — no `DJANGO_SETTINGS_MODULE`
export needed.

New behaviour needs a test. Time-dependent logic is the bulk of this package,
so lean on `freeze`-style fixtures or explicit `timezone.now() ± timedelta`
values rather than `sleep`.

## Linting

```console
$ uv run ruff check .
$ uv run ruff format --check .
```

Install the hooks to get this automatically:

```console
$ uv run pre-commit install
```

The hook set is `ruff` (with `--fix`), `ruff-format`, `pyupgrade
--py310-plus`, `django-upgrade --target-version 5.1`, plus whitespace and
private-key checks.

!!! note "Lint is advisory in CI"

    The `lint` job appends `|| true`, so style problems do not fail the build.
    Run the hooks locally anyway — a clean diff gets reviewed faster.

## Running the example project

```console
$ cd example
$ uv run python manage.py migrate
$ uv run python manage.py createsuperuser
$ uv run python manage.py runserver
```

It uses the working copy of the package, so it is the fastest way to see a
change end to end. Preview URLs render every blocked-page variant without
scheduling real downtime — see
[Blocked page](guide/blocked-page.md#testing-it-without-waiting).

## Documentation

```console
$ uv run --extra docs mkdocs serve
```

Live-reloading preview at <http://127.0.0.1:8000/>. Before pushing:

```console
$ uv run --extra docs mkdocs build --strict
```

`--strict` turns broken internal links and missing snippet files into
errors — the same check CI runs, so a green local build means a green
`Docs` job.

Conventions worth keeping:

- Pages live under `docs/` and must be listed in `nav:` in `mkdocs.yml`.
- Cross-references are relative links to the `.md` file
  (`../guide/banner.md#anchor`), never to the built URL — `--strict`
  validates them.
- `docs/changelog.md` includes the root `CHANGELOG.md` through a snippet.
  Edit the root file; the docs page has no content of its own.

## Continuous integration

Two workflows:

**`tests.yml`** — on every push and pull request to `main`:

- `test` — an 11-cell matrix (Django 5.2 on Python 3.10–3.14, Django 6.0 and
  6.1 on Python 3.12–3.14)
- `lint` — ruff check and format, advisory
- `example-check` — `manage.py check` and `migrate` against `example/`

**`docs.yml`** — builds the site with `--strict` on pull requests, and builds
plus publishes to GitHub Pages on pushes to `main`. Only paths that affect
the docs trigger it.

## Translations

See [Translations](guide/i18n.md#contributing-a-language-upstream) for the
`makemessages` / `compilemessages` cycle and what a clean translation PR
contains.

## Releasing

Maintainer checklist:

1. Update `CHANGELOG.md` — the format is
   [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versioning is
   [SemVer](https://semver.org/spec/v2.0.0.html).
2. Bump `version` in `pyproject.toml`.
3. Commit, tag `vX.Y.Z`, push both.
4. `uv build` and publish the artefacts from `dist/`.

The docs site redeploys on its own once the changelog change lands on `main`.

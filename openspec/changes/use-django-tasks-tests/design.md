## Context

See `proposal.md` for motivation and
`specs/django-tasks-test-compliance/spec.md` for the external contract.

Two different trees, easy to conflate:

```
Installed wheel (site-packages)
  django/tasks/              # library: Task, backends, …  NO tests.py / tests/

Django source (git tag = installed version)
  django/tasks/              # same library
  tests/tasks/               # Django's test package: tasks.py fixtures,
                             # test_tasks.py, test_dummy_backend.py, …
```

Django app tests are `tests.py` or a `tests/` package next to the app.
**Core** `django.tasks` does not follow that: tests sit in the project-level
`tests/tasks/` tree and are **not** on the wheel. pytest cannot “include
`django.tasks`” and discover tests inside it. It can include Django's
`tests/tasks/` once that tree is on the collection path.

This package already uses pytest with `settings.configure` in
`tests/conftest.py`. Redis is a testcontainer. Django's cases are
`SimpleTestCase` subclasses (`TaskTestCase`) that use `override_settings`,
`default_task_backend`, and Dummy/Immediate as the default `TASKS` backends.

## Goals / Non-Goals

**Goals:**

- Collect Django's applicable task tests through **pytest configuration**, as
  Django `SimpleTestCase`s, in the same `uv run pytest` run as the rest of
  this suite.
- Point Django's default task backend at `RedisBackend` plus the existing
  Redis testcontainer via Django settings, not by rewriting test methods.
- Keep Django's test files out of this git tree. Cache a throwaway copy
  locally as `.django-src-<version>_cache/` (gitignored via `.*_cache`);
  reuse it on later pytest runs; discard (or prune) that directory when
  Django is bumped. Exclude it from ruff and ty.

**Non-Goals:**

- Collecting Dummy, Immediate, or custom-backend test modules.
- Copying Django test files into this repo (vendor, submodule, snapshot).
- Re-hosting `TaskTestCase` methods as pytest functions.
- Replacing package-specific Redis/worker/handler tests.
- Running Django's `runtests.py` as a second command.

## Decisions

### Pytest collects Django's tests as Django tests

Treat Django's `tests/tasks/` as another pytest collection root. Do not wrap
or copy `TaskTestCase` methods. Configure pytest so Django's layout and
`SimpleTestCase` run natively:

- `python_files` includes Django's names (`test_*.py` and `tests.py`).
- Add **pytest-django** so `SimpleTestCase`, `override_settings`, and Django's
  async test methods work without a homegrown harness.
- A `DJANGO_SETTINGS_MODULE` (package `tests` settings) is the Django settings
  for the whole pytest run: `TASKS["default"]` is `RedisBackend`, `QUEUES`
  location is the Redis testcontainer. Existing tests keep passing against
  that settings module (migrate off ad-hoc `settings.configure` if it
  conflicts with pytest-django).
- Collection ignore (pytest `collect_ignore` / `norecursedirs` / path filter)
  drops `test_dummy_backend.py`, `test_immediate_backend.py`, and
  `test_custom_backend.py`. Dummy-only assertions still inside `TaskTestCase`
  (`default_task_backend.results`, default-is-Dummy, Immediate
  SUCCESSFUL-on-enqueue) are skipped at collection or via pytest marks, not
  rewritten into false passes.

**Alternative:** a hand-built adapter that imports selected methods.
Rejected: that is a second test suite, not Django's tests, and fights pytest
instead of configuring it.
**Alternative:** `python manage.py test` / Django `runtests.py`.
Rejected: this repo's default command is pytest; pytest-django is the bridge.

### Version-pinned local cache (fetch once per installed Django)

`django.tasks` has no tests on the wheel. Resolve Django **source** for the
exact installed version (`django.get_version()`) and put that
version's `tests/tasks/` tree on pytest's `pythonpath` as the `tasks`
package (`tasks.tasks`, `tasks.test_tasks`). Collect from that package (not
only this repo's `tests/`).

`django.get_version()` is the cache-dir and GitHub-tag key. Django omits a
trailing `.0`, so this is already upgrade-safe:

- 6.1.0 → `6.1` → `.django-src-6.1_cache` and tag `6.1`
- 6.1.1 → `6.1.1` → `.django-src-6.1.1_cache` and tag `6.1.1`
- 6.2.0 → `6.2` → `.django-src-6.2_cache` and tag `6.2`

A bump looks at a new directory; the old one is unused. Do not hard-code
`6.1` in the resolver.

Layout (shallow, one cache dir per version):

```
.django-src-6.1_cache/     # gitignored by .*_cache; name follows get_version()
  tasks/                   # Django's tests/tasks/ only
    __init__.py
    tasks.py
    test_tasks.py
    …
```

`pythonpath` includes `.django-src-<version>_cache` so `import tasks` is
Django's test package. Do not nest under `.cache/django-src/<version>/`.
Do not extract `django/`, `tests/runtests.py`, or `tests/test_utils/`.

The installed wheel already provides the library (`django.tasks`,
`django.test.SimpleTestCase`, Dummy/Immediate backends). Django 6.1's
`tests/tasks/` imports only `django.*` and relative `. import tasks`. It
does not need `runtests.py`, `test_utils`, or other project-test helpers.

Resolution order:

1. `DJANGO_TESTS_ROOT` if set (that checkout's `tests/` directory, so
   `DJANGO_TESTS_ROOT/tasks/` is the test package).
2. Gitignored `.django-src-<version>_cache/`. If `tasks/test_tasks.py`
   is already present, reuse it. Do **not** fetch or unpack on every
   pytest run.
3. On a miss for that version only: download the GitHub **tag archive**
   for `django.get_version()` (e.g.
   `https://github.com/django/django/archive/refs/tags/6.1.tar.gz`) and
   extract only members under `*/tests/tasks/` into
   `.django-src-<version>_cache/tasks/`. Prefer an atomic write (extract
   to a temp dir, then rename). Do not sparse-clone the whole Django repo.
4. Fail collection with a clear error if unresolved (unknown tag, network
   failure, empty `tasks/` tree).

When Django is upgraded, pytest looks at a **new** `.django-src-<new>_cache`
directory. Older `.django-src-*_cache` siblings MAY be deleted after the
current version resolves. They are never committed.

Exclude `.django-src-*_cache` from ruff (`extend-exclude`). ty already
limits `include` to `redis_tasks`, so it will not type-check the cache.

`pyproject.toml` cannot hard-code a versioned cache path. A pytest hook
(conftest / small plugin) registers the resolved path at configure time.
That hook is this repo's pytest config, not a copy of Django tests.

### How it folds into `uv run pytest`

Same process as today (`uv run pytest` / CI `uv run pytest -Walways -Werror`).
No second command, job, or marker. The cache is not a pytest plugin for Django;
it is an extra collection root registered at configure time.

1. **Configure (before collection).** `tests/conftest.py` (or a tiny local
   pytest plugin it loads) runs in `pytest_configure`:
   - Read `django.get_version()` from the installed wheel.
   - Resolve `DJANGO_TESTS_ROOT` or `.django-src-<version>_cache/` (fetch
     once on miss).
   - Insert the cache **root** on `sys.path` so `import tasks` is Django's
     test package.
   - If this run is the default suite (`config.args` is the ini `testpaths`,
     i.e. `tests/`, not an explicit file path), append that cache root (or
     `…/tasks/`) to `config.args` so pytest collects it.
   - `collect_ignore` / path filter drops `test_dummy_backend.py`,
     `test_immediate_backend.py`, `test_custom_backend.py`.
   - Method-level skips for Dummy `.results` / Immediate SUCCESSFUL-on-enqueue
     are registered here (names, not rewritten bodies).
2. **Django setup (same configure phase, pytest-django).**
   `DJANGO_SETTINGS_MODULE` points at a suite settings module:
   `TASKS["default"]` is `RedisBackend`. This replaces ad-hoc
   `settings.configure` so there is one setup path. pytest-django then runs
   `SimpleTestCase` natively (including Django's async test methods).
3. **Session: Redis testcontainer.** Django's `TaskTestCase` will not request
   today's `redis_url` / `task_queue` fixtures. A session-scoped (or autouse)
   fixture starts the existing Redis testcontainer, writes its URL into
   `settings.QUEUES[*]["LOCATION"]`, and clears queue records between tests
   the same way `task_queue` does. Package tests keep using that Redis.
4. **Collection.** Two roots in one run:
   - `tests/` — this package's tests (unchanged node ids).
   - `.django-src-<version>_cache/tasks/` — Django's `test_*.py` as unittest
     `TaskTestCase` nodes (`tasks/test_tasks.py::TaskTestCase::test_…`).
   An explicit path (`pytest tests/test_redis_backend.py`) does **not** pull
   in Django's suite; only the default command does.
5. **Run.** Failures from either root fail the same pytest process. ruff and
   ty are not invoked on the cache; they are separate tools and exclude it.

Cold cache: first default pytest for a version may hit the network during
`pytest_configure`. Later runs for that version are local and look like any
other extra test directory. Offline + missing cache fails collection with a
message that names the version and expected path.

### Default `TASKS` is RedisBackend

Django's `TaskTestCase` uses `override_settings(TASKS=...)` with Dummy as
default. The suite settings (or a pytest-django overlay for collected Django
modules) MUST set default `TASKS` to `RedisBackend` and Redis `QUEUES`
`LOCATION` to the testcontainer URL. Dummy and Immediate MAY remain as extra
aliases when a kept test still `using(backend=...)`. They MUST NOT be the
default backend under test.

Clear queue records between tests the same way `task_queue` does today.

## Risks / Trade-offs

- **[Risk] pytest-django + existing `settings.configure` conftest fight.** →
  Mitigation: one settings module for pytest-django; adjust package tests to
  use it rather than running two Django setup paths.
- **[Risk] `TaskTestCase.override_settings` still forces Dummy.** →
  Mitigation: pytest-django settings overlay or a subclass/conftest that
  replaces the default alias; skip methods that only make sense for Dummy or
  Immediate.
- **[Risk] Cold cache needs network.** → Mitigation: fetch only when
  `.django-src-<installed-version>_cache/` is missing; later pytest runs for
  the same version are local. `DJANGO_TESTS_ROOT` skips the cache. Fail loudly
  if missing and offline.
- **[Risk] Cache grows after Django bumps.** → Mitigation: directory name is
  `.django-src-<version>_cache`; old version dirs are discardable and MAY be
  pruned once the current version is resolved.
- **[Risk] ruff/format walks the cache.** → Mitigation: `extend-exclude`
  `.django-src-*_cache`; the directory is gitignored so pre-commit will not
  see it unless someone stages it.
- **[Trade-off] pytest-django is a new dev dependency.** Accepted: it is how
  pytest runs Django tests seamlessly.

## Migration Plan

Dev extra gains pytest-django and a Django settings module for pytest.
Package tests that relied on `settings.configure` in conftest move onto that
settings module if needed. Rollback: drop pytest-django, the collection hook,
and settings module; restore conftest `settings.configure`.

## Open Questions

None. `django.tasks` is the library; pytest collects Django's `tests/tasks/`
for the installed version as Django tests.

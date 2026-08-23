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
  locally in a directory pinned to the installed Django version; reuse it on
  later pytest runs; discard (or prune) that directory when Django is bumped.

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
exact installed version (`django.get_version()`, e.g. `6.1`) and add that
tree's `tests/` directory to pytest's `pythonpath` so `import tasks` is
Django's test package (`tasks.tasks`, `tasks.test_tasks`). Add `tests/tasks/`
to collection (not only this repo's `tests/`).

Resolution order:

1. `DJANGO_TESTS_ROOT` if set (local Django checkout's `tests/` directory).
2. Gitignored cache directory **named for that exact version**, e.g.
   `.cache/django-src/<version>/`. If that directory already contains a usable
   `tests/tasks/` tree, reuse it. Do **not** fetch or unpack on every pytest
   run.
3. On a miss for that version only: copy **`tests/tasks/`** from GitHub at
   the tag that matches the installed version (`django.get_version()`, e.g.
   tag `6.1`). Do **not** keep a full Django checkout in the cache. A sparse
   clone (`git clone --depth 1 --filter=blob:none --sparse --branch <tag>`
   then `git sparse-checkout set tests/tasks`) or extracting only that
   subtree from the tag archive is fine. Recursively materialize that
   directory into `.cache/django-src/<version>/`, then drop any leftover
   `.git` / unused archive members.
4. Fail collection with a clear error if unresolved (unknown tag, network
   failure, empty `tests/tasks/`).

When Django is upgraded, pytest looks at a **new** version directory. Older
sibling directories under the cache root are leftover and MAY be deleted
automatically after the current version resolves, so stale trees do not
accumulate. They are never committed.

`pyproject.toml` cannot hard-code a versioned cache path. A pytest hook
(conftest / small plugin) registers the resolved path at configure time.
That hook is this repo's pytest config, not a copy of Django tests.

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
  `.cache/django-src/<installed-version>/` is missing; later pytest runs for
  the same version are local. `DJANGO_TESTS_ROOT` skips the cache. Fail loudly
  if missing and offline.
- **[Risk] Cache grows after Django bumps.** → Mitigation: directory name is
  the installed version; old version dirs are discardable and MAY be pruned
  once the current version is resolved.
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

## Why

This package claims to be a Django `django.tasks` backend, but the suite only
has homegrown tests. Django already defines the task API and validates it in
`tests/tasks/`. Without those cases against `RedisBackend`, compliance is
inferred, not proven, and Django upgrades can change the contract unnoticed.

## What Changes

- Configure pytest to collect Django's `tests/tasks/` tree as Django tests
  (`SimpleTestCase`, pytest-django, `python_files` including `tests.py`). Do
  not commit those files and do not re-host test methods as pytest functions.
- Keep a gitignored throwaway copy of Django's **`tests/tasks/`** subtree
  only, in `.django-src-<version>_cache/` (matches `.*_cache` in
  `.gitignore`). On a cache miss, extract that path from the GitHub tag
  archive. Do not fetch or unpack on later pytest runs. When Django is
  upgraded, use a new directory and discard the old one. Do not keep a full
  Django checkout. Do not run ruff or ty on the cache.
- Collect only tests that apply to a third-party `BaseTaskBackend`. Do not
  collect DummyBackend, ImmediateBackend, or custom-backend modules.
- Default Django `TASKS` under pytest is `RedisBackend` plus the existing Redis
  testcontainer, not Dummy or Immediate.
- Skip cases that assume Dummy's in-memory `results` list or Immediate's
  synchronous SUCCESSFUL-on-enqueue behaviour.

## Capabilities

### New Capabilities

- `django-tasks-test-compliance`: The default test suite imports Django's
  applicable `django.tasks` tests for the installed Django version and runs
  them against `RedisBackend`.

### Modified Capabilities

None.

## Impact

- pytest config and a collection hook: pytest-django, settings module,
  `python_files`, path to Django's `tests/tasks/` for the installed version.
  No library API change. No vendored Django test files.
- Existing package tests may move from ad-hoc `settings.configure` onto that
  pytest-django settings module so there is one Django setup path.
- Failures become regressions of Django contract compliance, not optional extra
  jobs.

## 1. Pytest runs Django tests

- [x] 1.1 Add pytest-django and a `DJANGO_SETTINGS_MODULE` for the suite
      (`python_files` includes `test_*.py` and `tests.py`) and verify
      `SimpleTestCase` tests collect and run under `uv run pytest`.
- [x] 1.2 Point default `TASKS` at `RedisBackend` and `QUEUES` at the existing
      Redis testcontainer in that settings module, and verify
      `default_task_backend` is `RedisBackend` during collected Django tests.
- [x] 1.3 Move existing package tests off ad-hoc `settings.configure` if it
      conflicts with pytest-django, and verify `tests/test_redis_backend.py`
      still passes.

## 2. Collect Django's `tests/tasks/` for the installed version

- [x] 2.1 Resolve Django's `tests/tasks/` tree for `django.get_version()`
      (gitignored `.django-src-<version>_cache/tasks/`, else one GitHub
      tag-archive extract of `tests/tasks/` only into that cache) and register
      it on pytest's pythonpath/collection path; verify
      the cache is not a full Django checkout, `import tasks` is Django's
      test package, `tasks.test_tasks` is collected, and a second pytest run
      for the same version does not fetch again.
- [x] 2.2 Fail collection with a clear error when the tree cannot be resolved,
      and verify the message names the Django version and expected path.
- [x] 2.3 Ignore Dummy, Immediate, and custom-backend modules via pytest
      collect config; verify pytest does not collect `test_dummy_backend`,
      `test_immediate_backend`, or `test_custom_backend`.
- [x] 2.4 Confirm no Django test source is committed; verify `git ls-files`
      has no copy of Django's `tests/tasks/` files.
- [x] 2.5 After resolving the current version, unused sibling
      `.django-src-*_cache` directories are pruneable; verify a leftover
      `.django-src-<old-version>_cache/` is not used once Django is bumped.
- [x] 2.6 Exclude `.django-src-*_cache` from ruff; verify ruff/ty do not
      lint or type-check files in that directory.

## 3. Dummy/Immediate assertions inside TaskTestCase

- [x] 3.1 Skip Dummy `.results`, default-is-Dummy, Dummy `.clear()`, and
      Immediate SUCCESSFUL-on-enqueue / Immediate `TaskError` execution
      methods; verify those names are skipped or absent, not rewritten to pass.
- [x] 3.2 Leave Django's `module_path` assertions (`tasks.tasks.*`) intact and
      verify `import_string` round-trips Task instances from Django's fixture
      module.
- [x] 3.3 Clear queue records between Django `TaskTestCase` tests using the
      same pattern as `task_queue`, and verify consecutive enqueue tests do
      not share leftover entries.

## 4. Default-suite verification

- [x] 4.1 Run `uv run pytest` and verify Django's applicable `SimpleTestCase`
      contract tests run against Redis and pass with the rest of the package
      suite.
- [x] 4.2 Run ruff and ty on the pytest hook/settings and verify they pass.

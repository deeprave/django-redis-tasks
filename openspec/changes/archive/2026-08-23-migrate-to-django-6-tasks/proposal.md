## Why

This package targets the external `django_tasks` backport and maintains its own embedded Redis queue and asyncio worker loop. Django 6 now provides `django.tasks` as the supported task-definition, enqueueing, and result API, and the sibling `django-queues` package (1.0.0+) now provides a production-grade generic Redis/memory queue and worker layer, including its own `manage.py runqueues` command.

## What Changes

- Upgrade to Django 6.1+ and remove the `django_tasks` dependency.
- Add `django-queues>=1.0.0,<2.0.0` as a dependency and delete this package's embedded queue (`redis_tasks/taskqueue.py`) and worker loop (`redis_tasks/runqueue.py`), including the `AppConfig.ready()` worker-start hook.
- Implement `RedisBackend` as a thin `django.tasks.backends.base.BaseTaskBackend` that enqueues/looks up work through a configured `django_queue` `AsyncQueue` (typically `RedisAsyncPriorityQueueJson`), and a registered async `HANDLER` callable that `django-queues`' own `manage.py runqueues` command discovers and runs.
- Fix the pre-existing package-discovery break in `pyproject.toml` (setuptools flat-layout picks up `openspec/` as a top-level package) so the project is installable at all.

## Capabilities

### New Capabilities
- `django-6-redis-task-backend`: Enqueue and retrieve Django 6 task results through a `django-queues`-backed queue.

### Removed Capabilities
- `redis-tasks-embedded-queue`: The in-package Redis queue (`RedisTaskQueue`) and asyncio worker loop (`process_queues`/`start_task_queues`) are removed; `django-queues` owns storage and worker lifecycle instead.

### Modified Capabilities
None.

## Impact

Breaking dependency/API migration. Supersedes `add-django-task-worker-command` (removed): a worker command is no longer needed in this repo because `django-queues` already ships `manage.py runqueues`, which discovers any `QUEUES` alias configured with a `HANDLER` and runs it until cancelled.

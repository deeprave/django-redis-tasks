## 1. Dependencies and packaging

- [x] 1.1 Fix `pyproject.toml` package discovery so `openspec/` is not picked up as a top-level package (explicit `packages`/`include` for `redis_tasks` only), so the project installs at all.
- [x] 1.2 Replace `django_tasks>=0.6.1` with `django>=6.1` and add `django-queues>=1.0.0,<2.0.0` in `dependencies`.
- [x] 1.3 Update classifiers (`Framework :: Django :: 6.0`) and `requires-python` (`>=3.14`, `django-queues`' Python 3.14 floor applies transitively).

## 2. Remove the embedded queue and worker

- [x] 2.1 Delete `redis_tasks/taskqueue.py`, `redis_tasks/runqueue.py`, and their exports from `redis_tasks/__init__.py`.
- [x] 2.2 Remove the `start_task_queues()` call from `RedisTasksConfig.ready()`; drop the `asgiref`/`async_to_sync` import from `apps.py` (nothing else needed it).
- [x] 2.3 Delete `redis_tasks/signals.py`: `task_enqueued`/`task_started`/`task_finished` are no longer needed — `django.tasks.signals` and `django-queues` each provide their own equivalents.

## 3. Django 6 task backend

- [x] 3.1 Write failing tests for `RedisBackend.enqueue`, `get_result`, `validate_task` delegation, and status/error mapping, using a `django_queue` `RedisAsyncPriorityQueueJson` (via `testcontainers`, matching current `conftest.py` style).
- [x] 3.2 Implement `RedisBackend(BaseTaskBackend)` in `redis_tasks/backend.py`: settings-driven `queue_alias` lookup into `django_queue.queues`, JSON payload serialization, `supports_async_task = True`, `supports_get_result = True`, `supports_defer = False`, and `supports_priority = True` using `django-queues` 1.0.3's tracked priority enqueue path.
- [x] 3.3 Implement status mapping (`QueueEntryStatus` → `TaskResultStatus`) and error mapping (`QueueEntry.error` → `TaskError`) per design.md's table.
- [x] 3.4 Implement `redis_tasks/handlers.py::handle_task_entry`, the async `HANDLER` callable: resolves the task from the entry payload, constructs a `TaskResult`/`TaskContext` when required, calls sync or async tasks as appropriate, and returns a JSON-safe result for `django-queues` to store.
- [x] 3.5 Handle unimportable/invalid task functions in the handler by letting the exception propagate so `django-queues`' worker records it as `FAILED` with structured error detail (do not swallow silently).
- [x] 3.6 Add `redis_tasks.entries.TaskQueueEntry` with a durable `worker_ids` field; configure it through `QUEUES[alias]["ENTRY_CLASS"]`; and change `RedisTaskWorker._mark_running()` to append its UUIDv7 through the provider's atomic `amark_running()` transition. Map `TaskResult.worker_ids` from the entry field, not task payload.
- [x] 3.7 Add integration tests for the first dispatch and lease-recovery redelivery path, asserting that `TaskResult.attempts` is the length of the ordered `worker_ids` history (including repeated worker UUIDs). Verify entries stored before the field exists deserialize with `worker_ids=[]`.

## 4. Documentation

- [x] 4.1 Rewrite `README.md`: drop `django_tasks` install instructions, document the two-setting configuration (`QUEUES` for the `django-queues` alias + `HANDLER`, `TASKS` for the Django backend + `queue_alias` option), and `manage.py runqueues` as the worker entry point instead of automatic startup.
- [x] 4.2 Remove the stale root `TODO.md` entries superseded by this migration;
  document deferred scheduling as a current limitation in `README.md` and keep
  transient follow-up notes outside the tracked repository.
- [x] 4.3 Document the required `ENTRY_CLASS = redis_tasks.entries.TaskQueueEntry` and `WORKER = redis_tasks.worker.RedisTaskWorker` queue extensions, including that `worker_ids` is the ordered dispatch-attempt history and recovered entries may run more than once.

## 5. Cleanup superseded change

- [x] 5.1 Remove `openspec/changes/add-django-task-worker-command/` — superseded by `django-queues`' existing `manage.py runqueues` command; no new worker command is implemented in this repo.

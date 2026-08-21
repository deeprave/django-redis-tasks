## Context

Django 6 owns task declarations, enqueueing, and results through `django.tasks`. The sibling `django-queues` package (imported as `django_queue`, published on PyPI as `1.0.3`) owns generic named-queue storage and worker execution: `QUEUES` settings, `AsyncQueue`/`QueueEntry`/`QueueEntryStatus`, and the `manage.py runqueues` command that discovers any alias with a `HANDLER` and runs its worker until cancelled.

This package's only remaining job is translation: map Django's `Task`/`TaskResult`/`TaskResultStatus`/`TaskError` vocabulary onto `django-queues`' `QueueEntry`/`QueueEntryStatus` vocabulary, in both directions.

## Goals / Non-Goals

**Goals:**
- Implement `RedisBackend(BaseTaskBackend)` — `enqueue`, `get_result`, `validate_task` inherited behavior, and backend feature flags — using a `django_queue` `AsyncQueue` for storage.
- Implement one registered async `HANDLER` function that `runqueues` invokes per `QueueEntry`, executing the underlying task function (sync or async) and returning a JSON-safe result.
- Map `QueueEntryStatus` lifecycle and `QueueEntry.error` onto `TaskResultStatus` and `TaskError`.

**Non-Goals:**
- A worker process or management command in this repo — `django-queues`' `runqueues` already owns that.
- Reliable-delivery guarantees beyond what the configured `django_queue` backend provides (Redis async queues provide at-least-once delivery through claim leases and automatic recovery; this package does not add its own retry/claim logic).
- `run_after` deferral. `django_queue`'s `AsyncQueue.aenqueue(timeout_seconds=...)` accepts only an execution budget, not a delay-until time, so this package declares `supports_defer = False` and does not implement deferred scheduling itself (see Decisions).

## Decisions

### Backend construction and settings

`RedisBackend.__init__(self, alias, params)` receives Django's `TASKS[alias]` params (`BACKEND`, `QUEUES`, `OPTIONS`, per `BaseTaskBackend`'s own contract — `queues` there means *Django task* queue-name filtering, not a `django_queue` alias). This package adds one custom option read from `OPTIONS`: `queue_alias`, naming the `django_queue.queues` alias to delegate to (defaults to the Django task backend's own `alias` if omitted). The backend looks up `django_queue.queues[queue_alias]` lazily on first use — it does not construct its own `AsyncQueue`; that queue must already be configured in Django's `QUEUES` setting with a `RedisAsyncPriorityQueueJson`-family `BACKEND` and a `HANDLER` pointing at this package's handler.

This keeps queue construction, connection management, and validation entirely inside `django-queues`' existing `QueueRegistry` — this package never touches `redis.Redis` directly.

### Enqueue payload shape

`enqueue(task, args, kwargs)` builds a JSON-safe payload dict:

```json
{
  "func": "myapp.tasks.calculate_meaning_of_life",
  "args": [...],
  "kwargs": {...},
  "takes_context": false,
  "backend": "default",
  "queue_name": "default",
  "priority": 0
}
```

`task.priority` is passed to `django_queue.AsyncQueue.aenqueue()` and stored on the tracked `QueueEntry`; `RedisAsyncPriorityQueueJson` uses it to order dispatch. `supports_priority = True`.

`func` is `task.module_path` (already provided by Django's `Task`). `args`/`kwargs` are passed through Django's own `normalize_json` (as `TaskResult.__post_init__` already does) so they fail fast if not JSON-safe, matching `QueueEntry`'s own JSON-only contract.

`run_after` deferral: `django_queue.entries.QueueEntry` has no `run_after`/`not-before` concept — only `timeout_seconds`, an execution budget, not a delay. Supporting `supports_defer=True` therefore requires this package to hold `run_after` tasks itself rather than enqueueing them immediately: `enqueue()` stores the payload plus `run_after` in a small local scheduling structure and only calls `queue.aenqueue()` once `run_after` has passed. Given this package has no independent worker/loop after this migration, the simplest correct behavior for v1 is:

- **`supports_defer = False`** initially. `run_after` is out of scope for this change; a `run_after` task raises Django's own `InvalidTask` via `validate_task`, which is correct default `BaseTaskBackend` behavior when the flag is off.
- Deferred-task support becomes a follow-up change once `django-queues` or this package defines a delay primitive, avoiding a duplicate embedded scheduler loop (the thing this migration is removing).

This is a change from the current (pre-migration) behavior, which claims `supports_defer = True` but does not correctly implement scheduling either (see `TODO.md`: "while `run_after` is supported, currently there is no scheduling support"). Declaring the flag honestly is a correctness fix, not a regression.

### Result mapping

`get_result(result_id)` parses `result_id` as a UUID, calls `queue.find(entry_id)` (sync wrapper over `afind`), and raises `TaskResultDoesNotExist` when `django_queue.backends.exceptions.QueueEntryNotFoundError` is raised, or when `result_id` isn't a valid UUID.

Status mapping (`QueueEntryStatus` → `TaskResultStatus`):

| QueueEntryStatus | TaskResultStatus |
| --- | --- |
| `QUEUED` | `READY` |
| `RUNNING` | `RUNNING` |
| `SUCCEEDED` | `SUCCESSFUL` |
| `FAILED`, `TIMEOUT`, `CANCELLED` | `FAILED` |
| `TERMINATED` | not reachable — entries are pruned, not looked up, once terminated and past retention |

A `FAILED`/`TIMEOUT`/`CANCELLED` entry's `error` dict (`{"type": ..., "message": ...}`) becomes a single-element `errors: [TaskError(exception_class_path=..., traceback=...)]`. `django_queue`'s error dict has no traceback field (only `type`/`message`), so `TaskError.traceback` is synthesized as the message text — a documented limitation, not silently dropped data.

### Dispatch-attempt tracking

`redis_tasks.entries.TaskQueueEntry` subclasses `django_queue.entries.QueueEntry` and adds `worker_ids: list[str] = field(default_factory=list)`. Every queue delegated to by this backend MUST configure it through django-queues' `ENTRY_CLASS` setting. Redis queues receive that class during construction, so stored records are deserialized as `TaskQueueEntry`; the default makes records written before this field was introduced readable with an empty attempt history.

`RedisTaskWorker` overrides django-queues' `_mark_running()` hook. Once django-queues has claimed an entry, and immediately before it invokes the registered handler, the worker creates a replacement entry whose `worker_ids` is the existing list plus `str(self._worker_id)`. Both values are UUIDv7 strings; a worker ID identifies a worker process, whereas the entry ID identifies the task result.

The worker submits that replacement through the Redis provider's `amark_running()` operation. Its Lua script atomically verifies that the claim is still owned by that worker and that the stored entry is still `QUEUED`, then stores the complete `RUNNING` entry. If ownership was lost, the operation fails without writing a stale attempt record. The handler runs only after this operation succeeds.

Redis lease recovery automatically returns a non-terminal claimed entry to `QUEUED` while preserving custom entry fields. A later dispatch therefore appends another worker UUID. The same worker UUID may occur more than once if the same worker process reclaims a recovered entry. `TaskResult.worker_ids` maps directly from `entry.worker_ids`, making Django's `TaskResult.attempts` (`len(worker_ids)`) the exact number of handler executions for that queue entry.

### The registered HANDLER

`redis_tasks/handlers.py` defines:

```python
async def handle_task_entry(entry: QueueEntry) -> Any:
    payload = entry.payload
    task = task_from_payload(payload, payload.get("backend", entry.queue))
    result = task_result_from_entry(task, entry, task.backend)
    object.__setattr__(result, "status", TaskResultStatus.RUNNING)
    await task_started.asend(type(task.get_backend()), task_result=result)

    async def call_task() -> Any:
        if task.takes_context:
            return await task.acall(
                TaskContext(task_result=result), *payload["args"], **payload["kwargs"]
            )
        return await task.acall(*payload["args"], **payload["kwargs"])

    return normalize_json(await call_task())
```

This is imported via `QUEUES["<alias>"]["HANDLER"] = "redis_tasks.handlers.handle_task_entry"` in the consuming project's settings — `django-queues`' `runqueues` command imports and runs it; this package does not register it automatically, matching `django-queues`' existing opt-in pattern (a queue without `HANDLER` stays producer-only).

`RedisTaskWorker` emits `task_finished` with `asend()` only after
django-queues has durably settled the terminal entry. This gives all terminal
outcomes—including timeout and cancellation—a single post-persistence signal,
without reporting a recoverable interrupted handler as completed.

### App config

`RedisTasksConfig.ready()` no longer starts anything (no `start_task_queues()` call). It becomes a no-op or is removed entirely if it has nothing left to register — matching ADR 0001's "`AppConfig.ready()` only registers code" decision, already applied by `django-queues` itself.

## Risks / Trade-offs

- [Unimportable task function] → `import_string` failure in the handler is caught and recorded as a `FAILED` terminal entry with a structured error, mirroring `BaseTaskBackend.validate_task`'s own `is_module_level_function` check (which still runs at `enqueue()` time and rejects most of these before they're ever queued).
- [`run_after` / deferred tasks] → explicitly out of scope for this change (see Decisions above); `supports_defer = False`.
- [Worker identity / `attempts`] → requires both the package's `ENTRY_CLASS` and `WORKER` extensions. A stock django-queues worker can execute entries, but cannot supply the durable worker-process history Django's task result exposes.
- [At-least-once delivery] → inherited from django-queues' Redis claim leases and automatic recovery. A worker crash after a handler has begun can cause the same entry to execute again; task handlers must be idempotent where duplicate side effects matter. This package records those dispatches but does not add retry policy.

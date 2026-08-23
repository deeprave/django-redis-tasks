# django-6-redis-task-backend

## Purpose

Enqueue and retrieve Django 6 task results through a `django-queues`-backed Redis queue. This package translates `django.tasks` vocabulary onto a configured `django_queue` alias and a registered handler; `django-queues` owns storage and worker lifecycle.

## Requirements

### Requirement: Enqueue Django 6 tasks through a configured django-queues queue
The backend SHALL subclass `django.tasks.backends.base.BaseTaskBackend`, resolve a configured `django_queue` `AsyncQueue` by alias, enqueue a JSON-serializable payload describing the task call, and return a `TaskResult` whose `id` is the queue entry's ID.

#### Scenario: Enqueue a task
- **WHEN** a Django task is enqueued to the Redis backend
- **THEN** the backend returns a `TaskResult` with `status=READY` whose `id` identifies the underlying `django_queue` entry

#### Scenario: Enqueue an async task function
- **WHEN** a task wrapping a coroutine function is enqueued
- **THEN** the backend accepts it, since `supports_async_task` is `True`

#### Scenario: Reject deferred tasks
- **WHEN** a task is enqueued with `run_after` set
- **THEN** the backend raises `InvalidTask` via the inherited `validate_task` check, since `supports_defer` is `False`

#### Scenario: Enqueue priority tasks
- **WHEN** a task is enqueued with a queue-dispatch priority other than the default
- **THEN** the backend preserves the priority on the underlying `QueueEntry` for a priority-capable `django_queue` backend to dispatch

### Requirement: Retrieve task outcomes
The backend SHALL map a `django_queue` `QueueEntry` found by ID to a `TaskResult` with correct status and, for failures, structured error detail.

#### Scenario: Retrieve successful work
- **WHEN** a queued entry has `status=SUCCEEDED`
- **THEN** `get_result()` returns a `TaskResult` with `status=SUCCESSFUL` and `return_value` equal to the entry's `result`

#### Scenario: Retrieve failed work
- **WHEN** a queued entry has `status=FAILED`, `TIMEOUT`, or `CANCELLED`
- **THEN** `get_result()` returns a `TaskResult` with `status=FAILED` and one `TaskError` built from the entry's `error` dict

#### Scenario: Result does not exist
- **WHEN** `get_result()` is called with an ID that has no matching entry
- **THEN** the backend raises `TaskResultDoesNotExist`

### Requirement: Persist dispatch attempts
The Redis task queue SHALL use a `QueueEntry` descendant with a durable `worker_ids` list. Each successful `QUEUED` to `RUNNING` transition SHALL atomically append the UUIDv7 identifier of the worker process that owns the Redis claim. `TaskResult.worker_ids` SHALL be that list, and `TaskResult.attempts` SHALL consequently equal the number of recorded handler executions for the entry.

#### Scenario: First dispatch records its worker
- **WHEN** a worker claims a queued task entry and begins dispatch
- **THEN** the persisted running entry contains that worker's UUID in `worker_ids` before the handler is invoked

#### Scenario: Recovery records every execution attempt
- **WHEN** a worker's Redis claim expires after it has begun executing an entry and django-queues recovers the entry for another dispatch
- **THEN** recovery preserves the existing `worker_ids` list and the worker that next begins dispatch atomically appends its UUID
- **AND THEN** `TaskResult.attempts` equals the length of the resulting list, including repeated UUIDs when one worker process executes the entry more than once

### Requirement: Execute tasks via a django-queues HANDLER
The package SHALL provide an async callable importable as a `django_queue` `HANDLER`, which resolves the task function from the entry payload and executes it, returning a JSON-safe result for `django-queues` to persist.

#### Scenario: Execute a synchronous task function
- **WHEN** `django-queues`' worker dispatches an entry whose payload names a synchronous function
- **THEN** the handler calls it and returns its return value

#### Scenario: Execute an asynchronous task function
- **WHEN** `django-queues`' worker dispatches an entry whose payload names a coroutine function
- **THEN** the handler awaits it directly and returns its return value

#### Scenario: Execute a task that takes context
- **WHEN** a dispatched task declares `takes_context=True`
- **THEN** the handler constructs a `TaskResult` from the queue entry and passes its `TaskContext` to the task function

#### Scenario: Unimportable task function
- **WHEN** the entry payload's function reference cannot be imported
- **THEN** the handler raises, and `django-queues`' worker records the entry as `FAILED` with structured error detail

# Django Redis Tasks

[![Build Status](https://img.shields.io/github/actions/workflow/status/deeprave/django-redis-tasks/python-test-and-build.yml?branch=main&label=tests&logo=github)](https://github.com/deeprave/django-redis-tasks/actions/workflows/python-test-and-build.yml)
[![Security](https://img.shields.io/github/actions/workflow/status/deeprave/django-redis-tasks/codeql.yml?branch=main&label=security&logo=github)](https://github.com/deeprave/django-redis-tasks/security/code-scanning)
[![Maintenance](https://img.shields.io/badge/maintenance-active-brightgreen.svg)](https://github.com/deeprave/django-redis-tasks)
[![PyPI version](https://img.shields.io/pypi/v/django-redis-tasks.svg?logo=pypi&logoColor=white)](https://pypi.org/project/django-redis-tasks/)
[![PyPI downloads](https://img.shields.io/pypi/dm/django-redis-tasks.svg?logo=pypi&logoColor=white)](https://pypi.org/project/django-redis-tasks/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-redis-tasks.svg?logo=python&logoColor=white)](https://pypi.org/project/django-redis-tasks/)

This is a Redis-backed implementation of [Django's `django.tasks`](https://docs.djangoproject.com/en/6.1/topics/tasks/)
framework.

## django-queues

Queue storage and worker execution are provided by [`django-queues`](https://pypi.org/project/django-queues/), a
generic Django queue package. `django-redis-tasks` is a thin translation layer on top of it: it maps Django's task
vocabulary (`Task`, `TaskResult`, `TaskResultStatus`) onto `django-queues`' generic queue vocabulary (`QueueEntry`,
`QueueEntryStatus`), and provides the handler function that executes queued task calls.

This package does not manage Redis connections, run a worker loop, or start anything during Django's application
startup — `django-queues` owns all of that, including its `manage.py runqueues` management command.

## Deferred tasks

`run_after` is supported. The backend normalizes the datetime to UTC at enqueue: that UTC instant is stored on the task payload and passed to django-queues as `available_at`. Reconstruction therefore does not depend on the reader's `USE_TZ` or `TIME_ZONE`. Redis TIME decides when the entry becomes claimable; workers do not record an attempt or emit started/finished signals while the task is only waiting.

- **Aware datetimes** are converted to UTC.
- **Naive datetimes** are accepted only when `USE_TZ` is `False`; they are interpreted in Django's current timezone, then converted to UTC. When `USE_TZ` is `True`, Django rejects a naive `run_after` at enqueue. Legacy naive payload values are still normalized to UTC on read.
- A past or current `run_after` is eligible for dispatch immediately.
- A worker that has no due work waits until a deferred task becomes due; it does not busy-poll the application clock.

## Redis runtime

django-queues 1.2.0 requires **Redis 7+** and a deployed Function library before the application or a worker starts:

```shell
python manage.py redis_lua_lib --deploy
```

Queue aliases must match `[A-Za-z0-9_-]`. Redis keys from django-queues before 1.2.0 are not compatible; start from empty queue keys or a new Redis logical database.

## Installation

```shell
uv add django-redis-tasks
```

## Demo

A localhost dashboard under [`demo/`](demo/README.md) shows the Redis backend
live: pulse, summarise, and probe tasks, `run_after`, and a queue-observer
board. Start Redis with Compose, then `runserver` and `runqueues` as
documented there. It is not a production app.

## Configuration

`django_queue` must be added to `INSTALLED_APPS`. `redis_tasks` does not require
app registration today, but adding it is recommended for forward compatibility
with future Django integration points such as models, observer registrations,
templates, and static assets:

```python
INSTALLED_APPS = [
    ...
    "django_queue",
    "redis_tasks",
    ...
]
```

Configuration is two settings working together: `QUEUES` (owned by `django-queues`) configures the underlying Redis
queue and registers this package's handler; `TASKS` (owned by Django) configures the task backend and points it at
that queue.

```python
QUEUES = {
    "default": {
        "BACKEND": "django_queue.backends.redis.RedisAsyncPriorityQueueJson",
        "LOCATION": "redis://localhost:6379/12",
        "HANDLER": "redis_tasks.handlers.handle_task_entry",
        "ENTRY_CLASS": "redis_tasks.entries.TaskQueueEntry",
        "WORKER": "redis_tasks.worker.RedisTaskWorker",
    },
}

TASKS = {
    "default": {
        "BACKEND": "redis_tasks.backend.RedisBackend",
        "OPTIONS": {
            "queue_alias": "default",  # the QUEUES alias to delegate to; defaults to this TASKS alias
        },
    },
}
```

A Django project may configure multiple `QUEUES`/`TASKS` alias pairs, each backed by its own Redis queue.

`TaskQueueEntry` records `worker_ids` as the ordered history of worker-process UUIDs that began dispatching a task;
`TaskResult.attempts` is the length of that list. Redis automatically recovers an entry whose worker lease expires, so a
task can execute more than once. Make handlers with side effects idempotent.

## Running a worker

Task execution happens out-of-process, via `django-queues`' own management command:

```shell
python manage.py runqueues
```

This discovers every `QUEUES` alias with a `HANDLER` configured (including `redis_tasks.handlers.handle_task_entry`)
and runs its worker until the process receives a termination signal. Queue connections are initialized lazily when
their aliases are first used, but no task worker or handler execution starts in a Django web process — run `runqueues`
as a separate, standalone service.

## Async applications

`django-redis-tasks` supports Django's native asynchronous task API. In an
ASGI view, consumer, or other coroutine, use `await task.aenqueue(...)` to
write directly through django-queues' asynchronous Redis API. Refresh an
existing result with `await result.arefresh()`. Neither operation needs this
backend to cross Django's synchronous task-backend bridge, so queue I/O stays
on the caller's event loop.

```python
from django.http import JsonResponse


async def start_report(request):
    result = await build_report.aenqueue(request.user.pk)
    return JsonResponse({"task_id": result.id})


async def refresh_report(result):
    await result.arefresh()
    return result.status
```

Tasks declared with `async def` are also awaited directly by this package's
handler inside django-queues' worker event loop. A synchronous task function
is still safe, but Django runs it through a thread bridge to avoid blocking
that loop.

Queue work is deliberately outside the ASGI request runtime. The separate
`runqueues` service owns task dispatch and recovery, while django-queues'
process-local queue runtime owns lifecycle-observer delivery. This lets an
application use task status and best-effort queue observers without starting
workers from views or competing with request handling for an event loop.

An entirely asynchronous application should also use async middleware, views,
task functions, and task-signal receivers. Synchronous middleware, ORM work,
task functions, and signal receivers remain supported, but Django adapts those
specific boundaries through its thread bridge.

## Usage

Task definition, enqueueing, and result handling are Django's
[`django.tasks` API](https://docs.djangoproject.com/en/6.1/topics/tasks/).
This package provides the Redis backend; Django's documentation covers `@task`,
`enqueue` / `aenqueue`, and `TaskResult`.

A task is created using Django's `@task` decorator:

```python
from django.tasks import task


@task()
def calculate_meaning_of_life() -> int:
    return 42


@task()
async def nudge_nudge_wink_wink() -> list[str]:
    return ["say", "no", "more"]
```

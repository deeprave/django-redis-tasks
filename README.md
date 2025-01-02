from tests.settings import INSTALLED_APPS

# Django Redis Tasks

This is an implementation of django tasks using a Redis backend.

## django-tasks

This is an backend implementation for the [django-tasks](https://github.com/RealOnangeOne/django-tasks) module as defined in
[DEP 0014](https://github.com/django/deps/blob/main/accepted/0014-background-workers.rst).

It uses a redis store for task queues and storing the results of tasks, fully supports both sychronous functions and async
coroutines.

A limitation of this first implementation are:

- tasks are currently run sequentially until completion, meaning that long or forever running tasks may block subsequent
  tasks until they are completed. This will be corrected.
- while `run_after` is supported, currently there is no scheduling support.

The majority of the redis backed queue runs in async mode, and the async task runner is automatically started on when the
Django server starts.


## Installation
```shell
  pip install django-redis-tasks
```
```shell
  poetry add django-redis-tasks
```
```shell
  uv add django-redis-tasks
```
etc.

## Configuration

Both `django_tasks` and `redis_tasks` need to be added to `INSTALLED_APPS`.
```python
INSTALLED_APPS = [
    ...
    "django_tasks",
    "redis_tasks",
    ...
]
```

Django tasks are configured in the Django settings module, and use a simple and familiar configuration format similar to **DATABASES** and **CACHES**.

Example.

```python
TASKS = {
    "default": {
        "BACKEND": "redis_tasks.backend.RedisBackend",      # specify the backend for django.tasks
        "LOCATION": f"redis://localhost:6379/12",           # set the redis connection url and database
        "maxsize": 64,                                      # set the maximum number of tasks that can be queued
        "ttl": 3600,                                        # tasks are dispatched within the specified seconds, else they expire
        "queue_name": "task_queue",                         # set the queue name for this instance
    },
}
```

A Django server may support any number of task backends and should work alongside other types of backend, or multiple additional RedisBackend instances
using different queue_names.
The task runner iterates and dispatches tasks from all the registered redis tasks queues.
Tasks may select the queue or backend instance eligible to run them as outlined in the django-tasks documentation, otherwise they are added to the `default` backend.
By default, backend names are the alias assigned to them in the above configuration.

## Usage

A task is created using the @task decorator:
```python
from django_tasks import task


@task()
def calculate_meaning_of_life() -> int:
    return 42


@task(priority=10, queue_name="alternate")
async def nudge_nudge_wink_wink() -> list[str]:
    return ["say", "no", "more"]
```

> Note that currently the enqueue_on_commit task parameter is ignored.

## Why

`django-redis-tasks` needs a runnable, visual example that demonstrates its
Django task API, Redis priority dispatch, task results, and live lifecycle
updates together. The current unit tests verify individual contracts but do not
give users a small application they can run and inspect.

## What Changes

- Add a self-contained Django project under `demo/` that imports the adjacent
  `redis_tasks` package as an editable dependency and uses Redis through
  `django-queues`.
- Provide a browser dashboard with a small catalogue of safe, low-cost
  filesystem and data-summary tasks, selectable priority, task results, and
  live lifecycle updates.
- Enforce single-flight execution per task type: a task cannot be submitted
  again until its prior run reaches a terminal state, while other task types
  remain available to queue.
- Document local Redis, web-server, and worker startup using the established
  django-queues demo conventions.

## Capabilities

### New Capabilities

- `django-redis-tasks-demo`: A runnable Django dashboard that submits,
  observes, and presents Redis-backed Django tasks.

### Modified Capabilities

None.

## Impact

- Adds a separate `demo/` project, including its own dependency metadata,
  Docker Compose Redis service, Django app, templates/static assets, and
  documentation.
- Exercises the public `redis_tasks` backend and the `django-queues` observer
  API without changing the package's runtime API.

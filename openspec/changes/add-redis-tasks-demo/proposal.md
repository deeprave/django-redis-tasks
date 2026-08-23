## Why

The library has a working Django Tasks Redis backend, including deferred
`run_after` work, but no small application a user can run to see it. Unit
tests prove contracts; they do not show enqueue, dispatch, delay, or live
queue observation together. The neighbouring `django-queues` demos already
define the shape of that experience.

## What Changes

- Add a self-contained Django project under `demo/` that consumes this package
  as an editable dependency, following `demo_aq` / `demo_pq` in
  `../django-queues` (database-free, Docker Compose Redis, `runserver` plus
  `runqueues`, observer-backed dashboard, SSE).
- Demonstrate the Django Tasks API through this backend: a synchronous task,
  an asynchronous task, immediate enqueue, and deferred enqueue with
  `run_after`.
- Observe Redis-backed queue lifecycle through django-queues'
  `queue_observer` (the public API over Redis `aobserve`), not by polling
  Redis from the browser.
- Document local Redis, web, and worker startup in the same style as the
  django-queues demos.
- Supersede the unstarted `create-django-redis-tasks-demo` change (async-only,
  no `run_after`, outdated queue class names). Do not implement both.

## Capabilities

### New Capabilities

- `redis-tasks-demo`: A runnable Django demo that submits sync and async
  tasks, including `run_after`, and shows Redis queue lifecycle via an async
  queue observer.

### Modified Capabilities

None.

## Impact

- New `demo/` tree (pyproject, Compose Redis, Django project, dashboard,
  README). No change to the library's public task API.
- Demo depends on this package and `django-queues[redis]`; Redis is the only
  extra service.
- Archive or drop `openspec/changes/create-django-redis-tasks-demo` once this
  change is the demo source of truth, so two demo changes are not applied.

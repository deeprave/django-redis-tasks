## Context

See `proposal.md` for motivation and `specs/redis-tasks-demo/spec.md` for the
external contract. Neighbouring `django-queues` apps `demo_aq` and `demo_pq`
already show the operating pattern: no Django database, Compose Redis,
`runserver` plus `runqueues`, `queue_observer` projection, SSE to the browser.

This package's public surface is Django's Tasks API (`enqueue` / `aenqueue`,
`run_after`) plus `QUEUES`/`TASKS` wiring from the README. The unstarted
`create-django-redis-tasks-demo` change assumed async-only filesystem tasks
and older queue class names; this design replaces that approach.

## Goals / Non-Goals

**Goals:**

- Mirror django-queues demo process layout so someone who ran `demo_pq` can
  run this demo the same way.
- Enqueue only through Django's task API so the demo proves the backend, not
  a raw `queue.enqueue` bypass.
- Make sync vs async task functions, immediate vs `run_after`, and observer
  lifecycle all visible on one dashboard.

**Non-Goals:**

- Auth, multi-user isolation, durable dashboard history, or a monitoring
  product.
- Recurring schedules (`add-schedule-support`); only one-shot `run_after`.
- Custom demo workers that claim Redis entries outside `RedisTaskWorker` /
  `handle_task_entry`.
- Multi-process web-server coordination.

## Decisions

### Independent `demo/` project, django-queues layout

Create `demo/` with its own `pyproject.toml`, `uv.lock`, `manage.py`,
settings, Compose Redis, dashboard app, and README. Point the local
dependency at `..` as editable, the same way `demo_pq` points at
`django-queues`. Keeps demo deps out of the library and proves the package
is consumable.

**Alternative:** a docs-only example. Rejected: users cannot see Redis
lifecycle. **Alternative:** embed the demo in the library package. Rejected:
pollutes install metadata.

### Wire `TASKS` and `QUEUES` as the README does

Use `RedisAsyncPriorityQueueJson`, `TaskQueueEntry`, `RedisTaskWorker`,
`handle_task_entry`, and `RedisBackend` with a `demo` alias. Dashboard
submissions call `task.enqueue(...)` or `await task.aenqueue(...)`.

**Alternative:** enqueue via django-queues directly. Rejected: would not
demonstrate this package.

### Task catalogue: sync, async, immediate, delayed

Provide a small catalogue, for example:

- synchronous short task (CPU-trivial, returns a payload)
- asynchronous short task (`async def`, awaited in the worker)
- delayed variant (same work, `run_after` a few seconds in the future from
  a dashboard control)

Keep work cheap and deterministic (sleep/yield plus a JSON-normalizable
result). Optional filesystem summaries from the old demo plan are allowed if
they stay inside the demo directory; they are not required.

**Alternative:** faker injectors like `demo_pq`. Rejected: those enqueue
queue entries, not Django tasks, and hide `run_after`.

### Observer is `queue_observer` over Redis `aobserve`

Subscribe the dashboard process with `queue_observer("demo", ...)`. That is
django-queues' public API; Redis delivery uses `aobserve`. Keep a
process-local projection and stream full snapshots over SSE, copying
`demo_pq/dashboard/projection.py`. Do not query Redis from JavaScript.

**Alternative:** poll `get_result` from the browser. Rejected: misses
observer integration. **Alternative:** WebSockets. Rejected: extra stack for
one-way lifecycle events.

### ASGI dashboard, separate worker

Serve the dashboard with Django's ASGI `runserver` so an async submit path
can use `aenqueue`. Run `runqueues` in another terminal. Document a unique
localhost Redis port so this demo can sit beside `demo_aq` / `demo_pq`.

## Risks / Trade-offs

- [Observer projection is process-local] → Rebuild from retained-entry
  bootstrap on subscribe; document single web process.
- [Short `run_after` races Redis TIME vs wall clock] → Set delay from a
  clearly future offset (several seconds) and show remaining wait on the
  dashboard.
- [Users confuse this with `create-django-redis-tasks-demo`] → This change
  supersedes it; archive the old change when implementing.

## Migration Plan

1. Add `demo/` without changing the library API.
2. Start Redis via Compose, then `runserver` and `runqueues`.
3. Roll back by deleting `demo/`; no library migrations.

## Open Questions

None. Demo port, exact catalogue copy, and card layout can be chosen at
implementation without changing the spec.

## Context

See `proposal.md` for motivation and
`specs/django-redis-tasks-demo/spec.md` for the externally visible contract.
The neighbouring `django-queues` demos establish the repository convention for
a small database-free Django project, Docker Compose Redis, a process-local
observer projection, and Server-Sent Events (SSE).

The demo must exercise the public Django task interface exposed by
`redis_tasks`, not call a queue directly. Its worker is intentionally a normal
single-dispatch worker so selected priority determines the order of queued
work.

## Goals / Non-Goals

**Goals:**

- Make enqueueing, selected priority, lifecycle states, worker IDs, task
  results, and repeatable per-task submission visible in a browser.
- Keep work deterministic, bounded to the demo directory, and inexpensive.
- Demonstrate an entirely asynchronous request path and asynchronous task
  functions without adding a database or another message service.

**Non-Goals:**

- Authentication, multi-user isolation, durable dashboard history, or a
  production task-monitoring application.
- Progress percentages inside a running task; queue lifecycle transitions are
  the demonstration's live progress model.
- Multi-process web-server coordination. The demo documents its single web
  process assumption.

## Decisions

### Independent demo project

Create `demo/` with its own `pyproject.toml`, `uv.lock`, `manage.py`, Django
settings, Compose Redis service, dashboard app, and README. Point its local
dependency source at `..` as editable. This matches `demo_aq`, `demo_eq`, and
`demo_pq` in `django-queues`, keeps demo dependencies out of the library, and
proves that `redis_tasks` is consumable as a dependency.

### Task catalogue

Provide three `async def` Django tasks with fixed, visibly different bounded
durations (approximately one, ten, and thirty seconds): directory inventory,
file-extension summary, and source-text search. Each task only walks files
beneath the resolved demo root, skips transient directories, performs modest
I/O, and returns JSON-normalizable summary data. The deliberate asynchronous
wait makes state changes observable while the useful filesystem summary keeps
the work meaningful and avoids CPU-intensive calculations.

### Priority queue configuration

Configure `RedisAsyncPriorityQueueJson`, `TaskQueueEntry`, and
`RedisTaskWorker` under one `demo` queue alias, then configure Django `TASKS`
with `RedisBackend`. Each card supplies a bounded priority selector; the
submitted priority is shown in the dashboard and preserved in the task result.

### Observer projection and SSE

The dashboard process subscribes once to the `demo` queue with
`queue_observer`. Its lock-protected projection converts retained-entry and
lifecycle snapshots into JSON-ready rows and streams complete snapshots over a
long-lived SSE endpoint. Small browser JavaScript renders the state, selected
priority, worker attempts, result, and error from those snapshots.

SSE is chosen over polling because the demo is specifically illustrating
observer delivery and lifecycle updates. WebSockets add a server dependency
and bidirectional protocol that the page does not need; polling hides the
observer integration and delays visible state changes.

### Per-task single-flight gate

The projection indexes active entries by a logical catalogue task key embedded
in each task payload. The submission endpoint serializes check-and-enqueue with
a process-local lock: it rejects a request when an entry for that key is queued
or running, otherwise enqueues and records the new entry immediately. Observer
updates clear the active key on every terminal state. Cards use this state to
disable only their own submission form.

The lock and projection deliberately target the documented single-process demo
web server. A production multi-process implementation would need a Redis- or
database-backed admission control record.

## Risks / Trade-offs

- [Observer process restarts lose its in-memory projection] → Rebuild from the
  queue observer's retained-entry bootstrap and document that retention bounds
  the visible history.
- [A browser could bypass disabled controls] → Enforce the same per-task gate
  in the submission endpoint and return a clear conflict response.
- [Directory contents differ between machines] → Return summaries rather than
  asserting fixed content; keep each task inside the demo root and exclude
  virtual environments, cache directories, and VCS metadata.
- [The thirty-second task delays a queue] → This is intentional for priority
  and lifecycle visibility; use async waiting and keep the worker separate
  from the web process.

## Migration Plan

1. Add the standalone demo without modifying the library package API.
2. Start Redis through the demo Compose configuration, then run the Django web
   server and `runqueues` worker as separate local processes.
3. Roll back by removing the `demo/` directory; it has no migrations, database
   state, or effect on library users.

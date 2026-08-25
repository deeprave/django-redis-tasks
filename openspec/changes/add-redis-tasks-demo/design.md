## Context

See `proposal.md` for motivation and `specs/redis-tasks-demo/spec.md` for the
external contract. Neighbouring `django-queues` apps `demo_aq` and `demo_pq`
already show the operating pattern: no Django database, Compose Redis,
`runserver` plus `runqueues`, `queue_observer` projection, SSE to the browser.

This package's public surface is Django's Tasks API (`enqueue` / `aenqueue`,
`run_after`) plus `QUEUES`/`TASKS` wiring from the README. Recurring calendar
schedules (`add-schedule-support`) are a separate change; this demo chains
one-shot `run_after` enqueues instead.

## Goals / Non-Goals

**Goals:**

- Mirror django-queues demo process layout so someone who ran `demo_pq` can
  run this demo the same way.
- Enqueue only through Django's task API so the demo proves the backend, not
  a raw `queue.enqueue` bypass.
- Make sync vs async task functions, immediate vs delayed `run_after`,
  self-reschedule, and observer lifecycle all visible on one dashboard.
- Leave artefacts on disk (samples and a report under `demo/var/`) so a run
  is more than a status badge.

**Non-Goals:**

- Auth, multi-user isolation, durable dashboard history, or a monitoring
  product.
- Calendar / cron schedules (`add-schedule-support`).
- Custom demo workers that claim Redis entries outside `RedisTaskWorker` /
  `handle_task_entry`.
- Multi-process web-server coordination.
- Cheap sleep-only tasks whose only result is `"hello"`.

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

### Catalogue: pulse, summarise, probe

Three tasks, all doing work under `demo/var/` (or equivalent demo-local
storage):

1. **Pulse** (synchronous, self-rescheduling). Collect a local sample
   (demo directory size, sample count, Redis ping latency, or similar),
   append one JSON line to `demo/var/samples.jsonl`, then enqueue the next
   run with `run_after` a few seconds in the future unless a stop flag is
   set. Dashboard Start / Stop controls that flag (Redis key or demo file)
   so the chain cannot run away. Each run is a new queue entry (generation
   `pulse #n`), not one immortal row.

2. **Summarise** (asynchronous one-shot). Read the sample file, compute a
   small aggregate (count, min/max/mean of a numeric field), write
   `demo/var/report.json`. Dashboard offers **Run now** and **Run in ~15s**
   (`run_after`) so scheduled → due → running → artefact is visible.

3. **Probe** (synchronous, backoff). A check that fails until a precondition
   is met (for example, fewer than three samples). On failure it reschedules
   itself with a longer `run_after` (2s, 4s, 8s, capped). Success writes a
   short result and stops. Shows delay as a control, not just a wait.

**Alternative:** faker injectors like `demo_pq`. Rejected: those enqueue
queue entries, not Django tasks, and hide `run_after`. **Alternative:**
sleep-then-return-hello tasks. Rejected: they do not show why the backend
exists.

Self-reschedule is `task.using(run_after=...).enqueue()` at the end of a
successful (or backoff) run. It is not a stored schedule.

### Observer is `queue_observer` over Redis `aobserve`

Subscribe the dashboard process with `queue_observer("demo", ...)`. That is
django-queues' public API; Redis delivery uses `aobserve`. Keep a
process-local projection and stream full snapshots over SSE, copying
`demo_pq/dashboard/projection.py`. Do not query Redis from JavaScript.

**Alternative:** poll `get_result` from the browser. Rejected: misses
observer integration. **Alternative:** WebSockets. Rejected: extra stack for
one-way lifecycle events.

### Board: Scheduled / Done

The page is a catalogue of controls plus a live board:

- **Scheduled** — not yet terminal; deferred entries show remaining wait.
- **Done** — terminal result, error, and artefact path when present.

Ready and running are omitted. A local worker claims due work immediately and
these catalogue tasks finish in milliseconds, so those states never persist
long enough to paint. SSE snapshots drive the board; no full-page refresh.

Also show the pulse generation chain (`#1 → #2 → #3 waiting`) and a short
sparkline of recent sample values.

Each Django task run remains one queue entry.

### ASGI dashboard, separate worker

Serve the dashboard with Django's ASGI `runserver` so an async submit path
can use `aenqueue`. Run `runqueues` in another terminal. Document a unique
localhost Redis port so this demo can sit beside `demo_aq` / `demo_pq`.

## Risks / Trade-offs

- [Observer projection is process-local] → Rebuild from retained-entry
  bootstrap on subscribe; document single web process.
- [Short `run_after` races Redis TIME vs wall clock] → Set delay from a
  clearly future offset (several seconds) and show remaining wait on the
  board.
- [Pulse can run away if Stop is ignored] → Require an explicit stop flag
  checked at the end of each pulse; Start is the only way to enqueue the
  first generation.
- [Probe backoff vs pulse both use `run_after`] → Label generations and
  task names on the board so chains stay distinguishable.

## Migration Plan

1. Add `demo/` without changing the library API.
2. Start Redis via Compose, then `runserver` and `runqueues`.
3. Roll back by deleting `demo/`; no library migrations.

## Open Questions

None. Exact sample fields, probe precondition, Redis port, and CSS can be
chosen at implementation without changing the spec.

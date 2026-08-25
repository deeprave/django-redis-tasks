## Context

See `proposal.md` for the motivation and
`specs/deferred-django-tasks/spec.md` for the external contract. The backend
rejects `run_after` because `supports_defer` is false, not because the queue
lacks a delay primitive. django-queues 1.1.0 added `available_at: ClockTime` on
identified async enqueue; 1.2.0 (adopted floor) also requires a deployed Redis
Function library, Redis 7+, and a new Cluster hash-tagged key layout.

The Redis queue, not this package, owns the scheduled index and eligibility
decision. This backend only normalizes Django's `run_after` and passes it
through.

## Goals / Non-Goals

**Goals:**

- Make deferred work durable in Redis and available to any later worker via
  django-queues `available_at`.
- Use one public queue scheduling argument on both sync and async enqueue paths,
  with no application-side scheduler.
- Retain task payload metadata, result lookup, lifecycle signals, priority, and
  attempt tracking.
- Run tests and document ops against django-queues 1.2.0 Redis runtime.

**Non-Goals:**

- Add a general-purpose scheduler, cron syntax, recurrence, cancellation API,
  or a redis_tasks worker command.
- Implement scheduled ZSETs, promotion Lua, or Function-library code in this
  repo.
- Change at-least-once delivery after a task has become due.
- Support non-Redis queue backends for this backend.

## Decisions

### Consume django-queues `available_at` (do not add a delay API here)

Tracked `enqueue()`/`aenqueue()` on identified async queues accept optional
`available_at: ClockTime`. A future instant is stored as scheduled work and is
not claimable until Redis time (memory queues: queue clock) says it is due;
due work is promoted into normal pending/priority order atomically before
ordinary claim. Omitted or already-past instants dispatch immediately.

This backend converts a present `run_after` to UTC and passes
`available_at=ClockTime.from_datetime(...)`. It omits `available_at` when
`run_after` is unset. The entry record need not grow a Django-specific field:
the queue's scheduled index is the scheduling authority. The Django task
payload stores `run_after` as UTC ISO-8601 so reconstruction is independent of
the reader's `USE_TZ` and `TIME_ZONE`. Legacy naive payload values are
normalized to UTC on read, including when Django would otherwise raise
`InvalidTask` for a naive datetime.

No worker ID is appended and no task-started/finished signal is sent while an
entry is only scheduled. Crash recovery is unchanged: no claim exists yet.

| Entry state | Queue scheduling | Eligible for claim |
| --- | --- | --- |
| `QUEUED`, no future `available_at` | Normal pending | Yes |
| `QUEUED`, future `available_at` | Scheduled index | No |
| `QUEUED`, due `available_at` promoted | Normal pending | Yes |
| `RUNNING` or terminal | Not applicable | Not applicable |

### Normalize the due time at the backend boundary

`RedisBackend.validate_task()` runs with `supports_defer = True`, retaining
Django's module-level-function, priority, permitted task-queue-name, and aware
datetime validation. Before enqueueing, convert `run_after` to aware UTC:
aware values convert directly; when `USE_TZ=False`, naive values are made
aware in Django's current timezone then converted. The queue compares that
instant to Redis time; process-local wall clocks never decide availability.

### Keep enqueue and result semantics unchanged

Both `enqueue()` and `aenqueue()` pass the optional `ClockTime`, then fetch the
created entry and return a normal `READY` `TaskResult`. No new result status
or task-worker configuration. Immediate or past due times use the ordinary
pending path (queue default).

### Preserve priority

`priority=task.priority` remains on enqueue. django-queues 1.1.0+ promotes due
scheduled work by availability time, then priority within that group, then
arrival order. This package does not reimplement promotion.

### Adopt django-queues 1.2.0 Redis runtime

Minimum dependency: `django-queues[redis]>=1.2.0,<2.0.0`. Redis-backed queues
need Redis 7+ and the bundled Function library deployed (`redis_lua_lib
--deploy`) before app or worker start; `redis_lua_compat` checks FCALL.
Existing Redis queue keys from &lt;1.2.0 are not compatible (Cluster
hash-tagged aliases). Queue aliases stay ASCII `[A-Za-z0-9_-]` (`default` /
`alternate` already comply). Testcontainers fixtures must deploy the library
against the test Redis.

## Risks / Trade-offs

- [1.2.0 tests fail without Function deploy] → deploy in Redis test fixtures;
  document operator steps.
- [Pre-1.2.0 Redis data] → treat as a breaking runtime upgrade; wipe or do not
  reuse old queue keys.
- [Timezone conversion around DST] → naive datetimes via Django's current
  timezone, then one UTC instant.
- [Redis clock differs from caller clock] → Redis time is the documented
  authority; clients choose `run_after` from reliable, timezone-aware
  application time.

## Migration Plan

1. Raise django-queues to 1.2.0, enable `supports_defer`, map `run_after` to
   `available_at`.
2. Deploy Function library in tests; document Redis 7+ and key incompatibility.
3. Add unit and testcontainers coverage; replace the README `run_after`
   limitation.
4. Roll back by deploying the preceding package release; scheduled entries
   remain durable but need compatible django-queues to promote and dispatch.

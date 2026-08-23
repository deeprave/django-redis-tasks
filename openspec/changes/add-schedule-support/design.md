## Context

See `proposal.md` for motivation. `add-run-after-support` makes
`Task.using(run_after=...).enqueue()` durable on this backend. Django still
has no recurrence API. django-scheduled-tasks and django-crontask define
schedules as decorators around `@task` and run a **long-lived** scheduler
process (`run_task_scheduler`). This add-on copies that **declaration** shape
and implements the **runtime** as a Django task that re-enqueues itself with
`run_after`, which this backend can store in Redis.

Prerequisite: `supports_defer = True` and django-queues 1.2.0.

## Goals / Non-Goals

**Goals:**

- Opt-in module with `periodic_task` / `cron_task` matching django-scheduled-tasks
  (decorator above `@task`, or wrap an existing `Task` + `call_args`).
- One scheduler task: enqueue next self-tick first, then fan out due jobs.
- Durable last-run and a single-tick lease in Redis (same Redis as the queue).
- Skip-missed catch-up; bootstrap command that is safe to re-run.

**Non-Goals:**

- Replacing Celery Beat, Solar schedules, or task workflows/chaining.
- Catch-up of every missed occurrence.
- A long-running in-process scheduler loop (the django-scheduled-tasks model).
- Changing core `RedisBackend` enqueue for unscheduled tasks.
- Implementing delay in this package (queue `available_at` remains the primitive).

## Decisions

### Copy django-scheduled-tasks declaration API, not its process model

Public names and stacking order:

```python
@periodic_task(interval=timedelta(hours=2))
@task
def run_hourly(): ...


@cron_task(cron_schedule="0 9 * * *", timezone_str="Europe/Brussels")
@task
def daily_report(): ...


periodic_task(interval=timedelta(hours=3), call_args=("arg",), task=existing_task)
```

The outer decorator runs after `@task`, so it receives a `Task` and registers
it. Import-time registry; enabling the app autoloads `tasks` modules like
other Django autodiscover.

**Alternative:** long-running `run_task_scheduler` (django-scheduled-tasks).
Rejected: we already have durable `run_after`; a second process duplicates
workers. **Alternative:** crontab-only (django-crontask). Rejected: interval
jobs are the common case and the reference API includes both.

### Scheduler is a task; next tick is enqueued first

Tick body:

1. Try to acquire a Redis lease (SET NX with TTL > worst-case tick).
2. If acquired: enqueue `scheduler.using(run_after=now+tick).enqueue()`.
3. Load registry + last-run hash; for each job, if due, enqueue the target
   `Task.using(run_after=fire_at)` (omit `run_after` when `fire_at <= now`).
4. Write last-run for fired jobs; release lease (TTL still covers crashes).

Tick interval: default 60s, or sooner if the next cron/interval fire is
sooner, capped by a minimum floor (e.g. 1s) to avoid a tight loop.

**Alternative:** pass last-run only in scheduler kwargs. Rejected: two
bootstraps or a lost payload desynchronize state. Redis last-run is the
source of truth.

### Job identity and last-run

Job key: `task_path` + canonical JSON of `call_args` (and empty kwargs).
Last-run: Redis hash field = UTC epoch. Missing field = never run → first
due time is "now" for interval (fire on first tick) and next cron occurrence
from "now" (do not fire immediately unless the cron matches this minute).

Interval: due when `last_run + interval <= now` (or never run).
Cron: five-field expression via `croniter`; timezone is `timezone_str` or
Django current timezone; next/previous occurrence in that zone, stored as UTC.

Catch-up: if several windows were missed, fire once at `now` (or the most
recent occurrence) and set last-run to now. Do not enqueue N delayed copies.

### Lease and bootstrap

Lease key per Django `TASKS` alias / queue alias so multiple backends do not
share ticks. Bootstrap: `manage.py enqueue_task_scheduler` (name TBD in
implementation) checks for an existing pending scheduler entry (or lease +
scheduled `run_after`); if none, enqueues one immediate scheduler task.

**Alternative:** start the chain from `AppConfig.ready()`. Rejected: web
processes would enqueue ticks; operators should start it beside `runqueues`.

### Packaging

Optional extra `[schedule]` if `croniter` (or equivalent) should not sit on
the core install. Interval-only could work without it; v1 includes cron, so
depend on a crontab parser in that extra or as a hard optional import with a
clear error.

Export from `redis_tasks.schedule` so apps can `from redis_tasks.schedule
import periodic_task, cron_task` without installing a second product. App
label e.g. `redis_tasks` already recommended; autodiscover gated on a setting
`REDIS_TASKS_SCHEDULE = True` or a separate tiny app `redis_tasks.schedule`
in `INSTALLED_APPS`. Prefer a setting plus autodiscover from the existing app
to avoid a second app — unless Django autodiscover is cleaner as
`redis_tasks.schedule` in INSTALLED_APPS (mirrors django-scheduled-tasks).
**Choose:** `redis_tasks.schedule` in `INSTALLED_APPS` for explicit opt-in,
same as the reference package.

## Risks / Trade-offs

- [Duplicate scheduler chains] → bootstrap idempotency + Redis lease; document
  "one bootstrap per deploy/environment".
- [Tick holds lease while fan-out is slow] → lease TTL > tick + enqueue budget;
  extend lease if needed.
- [At-least-once child jobs] → same as the rest of the backend; jobs must be
  idempotent. Lease only prevents two ticks, not worker redelivery of a child.
- [Clock skew vs cron timezone] → evaluate cron in declared timezone; compare
  using Redis/queue time converted to that zone.
- [add-run-after-support not landed] → this change is blocked on `run_after`;
  implement after or behind that pin.

## Migration Plan

1. Land `add-run-after-support` (or implement against that contract).
2. Ship the add-on disabled by default; apps add `redis_tasks.schedule` to
   `INSTALLED_APPS`, decorate tasks, run bootstrap beside `runqueues`.
3. Roll back by stopping bootstrap and removing the app; in-flight scheduled
   children still run; the chain dies when no further scheduler tick is
   enqueued (or after TTL). No Redis schema beyond keys with a package prefix
   (delete-safe).

## Open Questions

- Exact bootstrap command name (`enqueue_task_scheduler` vs
  `run_task_scheduler` that only enqueues once). Prefer the former so it is
  not confused with a blocking loop.
- Whether first interval fire is immediate or after one full interval. Spec
  says never-run interval fires on first due tick (immediate). Confirm in
  implementation tests.

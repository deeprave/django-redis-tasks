## Why

Django's task framework has no recurrence or cron API. After `run_after` is
supported, apps can still only enqueue one-shot deferred work. Periodic jobs
need either a third-party beat process or a small add-on that reuses this
backend's deferred enqueue. We can ship that add-on in this package: a
self-rescheduling scheduler task plus a schedule-definition API matching
existing Django-tasks proposals (`periodic_task` / `cron_task` wrapping
`@task`).

## What Changes

- Add an **opt-in** schedule add-on (not required to use `RedisBackend`).
- Let apps declare periodic and crontab schedules with the same decorator
  shape as django-scheduled-tasks: `@periodic_task(interval=...)` /
  `@cron_task(cron_schedule=..., timezone_str=...)` above `@task`, plus
  calling `periodic_task(..., task=existing, call_args=...)` for already-defined
  tasks.
- Run scheduling as a single Django task that enqueues itself with
  `run_after` for the next tick, records last-run times, and enqueues due jobs
  via `using(run_after=...)`.
- Provide bootstrap to start the scheduler chain (management command), a
  Redis lease so only one tick is active, and skip-missed catch-up (late tick
  runs the last due occurrence, not a backlog).
- Document the add-on, its dependency on `supports_defer`, and that it is
  not a general Celery Beat replacement.

## Capabilities

### New Capabilities

- `scheduled-django-tasks`: Opt-in periodic and crontab scheduling for
  Django tasks on this Redis backend, driven by a self-rescheduling
  scheduler task.

### Modified Capabilities

None.

## Impact

- New optional module (schedule registry, scheduler task, management command,
  Redis last-run/lease keys). `INSTALLED_APPS` entry for autodiscovery.
- Depends on `add-run-after-support` (`supports_defer = True` and
  django-queues 1.2.0 `available_at`).
- Possible extra dependency for crontab parsing (e.g. `croniter`) as an extra
  or optional requirement.
- README/changelog. No change to the core enqueue path for unscheduled tasks.

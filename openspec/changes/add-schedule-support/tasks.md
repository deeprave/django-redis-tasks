## 1. Opt-in package wiring

- [ ] 1.1 Add `redis_tasks.schedule` as an optional Django app (AppConfig) and a
      `[schedule]` extra that depends on `croniter` (or equivalent); verify
      `INSTALLED_APPS` without it leaves core backend imports and tests green.
- [ ] 1.2 Autodiscover `tasks` modules when the schedule app is installed;
      verify a decorated task in an installed app's `tasks.py` appears in the
      in-process registry after Django setup.

## 2. Schedule declaration API

- [ ] 2.1 Implement `periodic_task(interval=..., call_args=(), task=None)` as a
      decorator-above-`@task` and as a function wrapping an existing `Task`;
      verify stacked-decorator and `task=` registration tests, and that a
      non-positive interval raises at registration.
- [ ] 2.2 Implement `cron_task(cron_schedule=..., timezone_str=None, ...)` with
      the same stacking/`task=` shape; verify five-field cron + timezone tests
      and that an invalid expression raises at registration.
- [ ] 2.3 Persist `call_args` on the registry entry and use them on enqueue;
      verify the wrapped existing-task scenario from the spec.

## 3. Scheduler tick

- [ ] 3.1 Implement the scheduler Django task: acquire Redis lease, enqueue the
      next self-tick with `run_after` first, then fan out due jobs; verify a
      unit test that the next scheduler enqueue happens before job fan-out.
- [ ] 3.2 Implement last-run Redis hash and due logic (never-run interval fires
      on first tick; cron next occurrence; skip-missed); verify interval and
      cron due tests including a multi-window downtime case that enqueues once.
- [ ] 3.3 Implement single-tick lease so overlapping scheduler entries do not
      double-enqueue jobs; verify a concurrency test with two overlapping ticks.
- [ ] 3.4 Fail clearly when `supports_defer` is false; verify the scheduler does
      not enqueue jobs in that case.

## 4. Bootstrap

- [ ] 4.1 Add `enqueue_task_scheduler` management command that enqueues one
      scheduler task if none is pending; verify first-run enqueues and a second
      invocation does not start a second chain.

## 5. Verification and docs

- [ ] 5.1 Add testcontainers coverage: bootstrap → worker → interval/cron job
      enqueued at the expected time using `run_after`; verify the spec
      scenarios for due jobs, future `run_after`, restart of last-run, and
      skip-missed.
- [ ] 5.2 Document the add-on in the README (decorator examples matching
      django-scheduled-tasks, `INSTALLED_APPS`, `enqueue_task_scheduler` beside
      `runqueues`, defer prerequisite, skip-missed, idempotent jobs) and add a
      changelog entry.
- [ ] 5.3 Run repository quality gates: Ruff check/format, ty, pytest with
      `-Walways -Werror`, osvcheck, validate-pyproject, and strict OpenSpec
      validation.

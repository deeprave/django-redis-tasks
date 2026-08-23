## Purpose

Provide an opt-in add-on that declares interval and crontab schedules for Django
tasks and drives them with a self-rescheduling scheduler task on this Redis
backend, without a third-party beat process.

## ADDED Requirements

### Requirement: Declare interval and crontab schedules around Django tasks
The add-on SHALL let an application register a Django `Task` on an interval
schedule or a five-field crontab schedule. The public shape SHALL match existing
Django-tasks schedule proposals: a schedule decorator placed above `@task`, and
an equivalent function call that accepts an existing `Task` plus optional
positional call arguments. Crontab schedules SHALL accept an optional timezone
identifier (`timezone_str`); when omitted, Django's current timezone SHALL be used.

#### Scenario: Interval schedule via stacked decorators
- **WHEN** an application places an interval schedule decorator above `@task`
  with a positive `timedelta`
- **THEN** that task is registered as a periodic job using that interval

#### Scenario: Crontab schedule with timezone
- **WHEN** an application places a crontab schedule decorator above `@task`
  with a five-field cron expression and an optional `timezone_str`
- **THEN** that task is registered as a cron job evaluated in that timezone
  (or Django's current timezone if `timezone_str` is omitted)

#### Scenario: Register an existing task with call arguments
- **WHEN** an application calls the interval helper with an already-defined
  `Task`, an interval, and positional call arguments
- **THEN** each scheduler-driven enqueue of that job SHALL pass those arguments

#### Scenario: Invalid schedule definition
- **WHEN** an application registers a non-positive interval or an invalid
  crontab expression
- **THEN** registration fails with an error before the scheduler runs

### Requirement: Opt-in add-on that requires deferred enqueue
The schedule add-on SHALL be optional. Applications that only use the Redis
task backend SHALL NOT need to enable it. Enabling the add-on SHALL require a
backend with deferred enqueue (`run_after`) support. If the scheduler starts
without that support, it SHALL fail clearly and SHALL NOT enqueue jobs.

#### Scenario: Backend without the add-on
- **WHEN** an application configures `RedisBackend` and does not enable the
  schedule add-on
- **THEN** enqueue, results, and workers behave as they do without this change

#### Scenario: Scheduler started without defer support
- **WHEN** the scheduler runs against a backend that rejects `run_after`
- **THEN** it fails with a clear error and does not enqueue scheduled jobs

### Requirement: Drive due jobs from a self-rescheduling scheduler task
The add-on SHALL enqueue due jobs through Django's task API using `run_after`
when the next fire time is in the future, or as immediately eligible work when
the fire time is now or past. The scheduler itself SHALL be a Django task that
enqueues its next run with `run_after` so the chain continues as long as workers
process the queue. A late scheduler tick SHALL enqueue at most the latest due
occurrence per job (skip missed windows), not a backlog of missed fires.

#### Scenario: Due interval job is enqueued
- **WHEN** a scheduler tick runs and an interval job's next fire time is at or
  before the queue's current time
- **THEN** that job is enqueued once with its registered arguments

#### Scenario: Future cron job uses run_after
- **WHEN** a scheduler tick determines a cron job's next fire time is in the
  future
- **THEN** it enqueues that job with `run_after` set to that instant and does
  not invoke it immediately

#### Scenario: Scheduler continues after a tick
- **WHEN** a scheduler tick starts
- **THEN** it first enqueues the next scheduler tick with `run_after` at the
  next tick instant so a later failure while fanning out jobs does not stop
  the chain

#### Scenario: Workers were down across several windows
- **WHEN** the scheduler next runs after downtime spanning multiple cron or
  interval windows
- **THEN** each job is enqueued at most once for the latest due occurrence

### Requirement: Persist last-run times and keep a single active tick
The add-on SHALL persist each job's last fire time durably so a new worker can
continue the schedule after restart. Concurrent scheduler ticks SHALL NOT both
fan out the same due jobs; a lease or equivalent SHALL allow only one tick to
enqueue jobs at a time.

#### Scenario: Last-run survives worker restart
- **WHEN** a job has been fired and all workers stop, then a worker starts later
- **THEN** the scheduler uses the persisted last fire time and does not treat
  the job as never-run

#### Scenario: Two scheduler entries become due
- **WHEN** two scheduler tasks become eligible at the same time
- **THEN** only one tick enqueues scheduled jobs; the other does not duplicate
  those enqueues

### Requirement: Bootstrap the scheduler chain
The add-on SHALL provide a management command that enqueues the scheduler if it
is not already pending, so operators can start the chain after deploy. The
command SHALL be idempotent: a second invocation SHALL NOT create a second
unbounded chain when a tick is already scheduled.

#### Scenario: First start after deploy
- **WHEN** an operator runs the bootstrap command and no scheduler tick is
  pending
- **THEN** one scheduler task is enqueued (immediately eligible or with a short
  `run_after`)

#### Scenario: Bootstrap when a tick is already scheduled
- **WHEN** an operator runs the bootstrap command and a scheduler tick is
  already pending
- **THEN** the command succeeds without enqueueing another scheduler tick

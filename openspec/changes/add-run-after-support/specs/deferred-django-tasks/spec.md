## Purpose

Provide durable, Redis-timed deferred execution for Django tasks while retaining
the normal task result, priority, and worker lifecycle contract.

## ADDED Requirements

### Requirement: Enqueue a task for its earliest execution time
The backend SHALL support a task whose `run_after` is set, persist it durably,
and return its `TaskResult` immediately with `status=READY`. The task SHALL not
be dispatched before its requested earliest execution time, including after an
application or worker restart.

#### Scenario: Enqueue a future task
- **WHEN** a caller enqueues a task with a future `run_after`
- **THEN** the backend returns a `READY` result whose ID can be used to retrieve
  that still-pending task
- **AND THEN** no worker invokes the task before the requested time

#### Scenario: A deferred task survives process restart
- **WHEN** a task is enqueued for a future time and the enqueuing process or all
  workers stop before that time
- **THEN** a worker started after the requested time dispatches the persisted
  task exactly as normal queue work, subject to the queue's at-least-once
  delivery semantics

#### Scenario: A past or current task is available immediately
- **WHEN** a caller enqueues a task whose `run_after` is at or before the
  queue's current time
- **THEN** the task is available for normal dispatch without an avoidable delay

### Requirement: Use a consistent clock and timezone interpretation
The backend SHALL interpret a `run_after` datetime according to Django's
timezone settings, normalize the resulting due time to UTC, persist that UTC
instant on the task payload, and use Redis time as the authority for durable
availability decisions. It SHALL reconstruct `run_after` as that UTC instant,
independent of the reader's `USE_TZ` and `TIME_ZONE`. Legacy naive payload
values SHALL be normalized to UTC on read rather than raising Django's
invalid-task error.

#### Scenario: Timezone-aware deferred task
- **WHEN** a caller supplies an aware `run_after` in any timezone
- **THEN** the task becomes available at the equivalent UTC instant

#### Scenario: Naive datetime with timezone support disabled
- **WHEN** Django timezone support is disabled and a caller supplies a naive
  `run_after`
- **THEN** the backend interprets it using Django's current timezone before
  normalizing it to UTC

#### Scenario: Naive datetime with timezone support enabled
- **WHEN** Django timezone support is enabled and a caller supplies a naive
  `run_after`
- **THEN** enqueueing fails with Django's invalid-task validation error

#### Scenario: Reconstruction is independent of reader timezone settings
- **WHEN** a deferred task is reconstructed after `USE_TZ` or `TIME_ZONE` has
  changed from the enqueueing process
- **THEN** the result's `run_after` is the same UTC instant that was stored

#### Scenario: Legacy naive payload under timezone support
- **WHEN** a stored payload has a naive `run_after` and Django timezone support
  is enabled
- **THEN** reconstruction succeeds with that instant normalized to UTC rather
  than raising Django's invalid-task error

### Requirement: Retain normal queue and worker lifecycle semantics
The backend SHALL enqueue a deferred task by passing the normalized due instant
to the configured django-queues tracked enqueue as `available_at`, so the entry
is ineligible for ordinary claim before its `run_after` time. The queue SHALL
atomically promote a due task to normal pending/priority ordering before an
ordinary claim. It SHALL make the normal `QUEUED` to `RUNNING` transition only
after claim, then dispatch the handler. It SHALL not record a worker ID or emit
task-started/task-finished signals merely while an entry is deferred.

#### Scenario: A queued entry has a future availability instant
- **WHEN** a task is enqueued with a future `run_after`
- **THEN** its durable record is atomically indexed as scheduled rather than
  normal pending work
- **AND THEN** it remains `QUEUED` and its result remains `READY` until due

#### Scenario: Worker selection before a task is due
- **WHEN** a worker attempts to claim work before a deferred task is due
- **THEN** the queue does not return that task as claimable work
- **AND THEN** the worker continues selecting other eligible tasks

#### Scenario: Due task becomes ordinary queue work
- **WHEN** a worker claims work at or after a deferred task's scheduled time
- **THEN** the queue atomically moves the task into its normal pending or
  priority ordering
- **AND THEN** the ordinary claim and dispatch lifecycle proceeds unchanged

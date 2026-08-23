## Purpose

Give developers a small, runnable Django app that shows this package's Redis
task backend: sync and async tasks, deferred `run_after` work, and live Redis
queue observation without treating the unit tests as the only example.

## ADDED Requirements

### Requirement: Self-contained demo project

The repository SHALL provide a Django project under `demo/` with its own
dependency metadata and local Redis startup instructions. The demo SHALL use
the adjacent package as a dependency rather than copying the backend.

#### Scenario: Start the demonstration
- **WHEN** a developer follows the demo README's Redis, web-server, and worker
  commands
- **THEN** they can open a local dashboard backed by the configured Redis task
  queue

### Requirement: Synchronous and asynchronous tasks

The demo SHALL expose at least one synchronous Django task and at least one
asynchronous Django task. Both SHALL be enqueueable from the dashboard and
SHALL return a result the dashboard can display.

#### Scenario: Submit a synchronous task
- **WHEN** a user submits the synchronous catalogue task
- **THEN** the dashboard records a queued result and later shows a successful
  result after a worker runs it

#### Scenario: Submit an asynchronous task
- **WHEN** a user submits the asynchronous catalogue task
- **THEN** the dashboard records a queued result and later shows a successful
  result after a worker awaits that task

### Requirement: Immediate and deferred enqueue

The demo SHALL allow immediate enqueue and enqueue with a future `run_after`.
A deferred task SHALL remain undispatched until its due time.

#### Scenario: Immediate enqueue
- **WHEN** a user submits a catalogue task without a delay
- **THEN** a worker may claim it as soon as it is pending

#### Scenario: Deferred enqueue
- **WHEN** a user submits a catalogue task with a future `run_after`
- **THEN** the dashboard shows that work as waiting until the due time
- **AND** a worker does not run it before that time

### Requirement: Live Redis queue observation

The dashboard SHALL observe Redis queue lifecycle through django-queues'
async queue observer API. It SHALL NOT poll Redis from the browser. It SHALL
update queued, running, and terminal states without a full-page refresh.

#### Scenario: Observe a successful run
- **WHEN** a submitted task is claimed and completes successfully
- **THEN** the browser receives live queued and running updates followed by
  the final result

#### Scenario: Observe deferred work becoming due
- **WHEN** a deferred task's `run_after` is reached
- **THEN** the dashboard shows it becoming claimable and then running without
  a full-page refresh

### Requirement: Demo operating conventions

Startup SHALL match the neighbouring django-queues demos: Docker Compose for
Redis, `runserver` for the dashboard, and `runqueues` as a separate worker
process. The demo SHALL be database-free aside from Redis.

#### Scenario: Documented three-process workflow
- **WHEN** a developer starts Redis, the web server, and `runqueues` as
  documented
- **THEN** submitting a task from the dashboard produces worker execution and
  observer updates

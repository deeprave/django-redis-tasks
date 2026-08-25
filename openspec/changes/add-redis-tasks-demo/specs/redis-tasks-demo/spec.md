## Purpose

Give developers a small, runnable Django app that shows this package's Redis
task backend on a live page: meaningful sync and async work, immediate and
delayed `run_after`, self-rescheduling chains, and Redis queue observation
without treating the unit tests as the only example.

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

### Requirement: Meaningful catalogue tasks

The demo SHALL expose three catalogue tasks that perform demo-local work,
not sleep-only placeholders:

- a synchronous **pulse** that records a sample artefact and may enqueue
  its next run
- an asynchronous **summarise** task that reads those samples and writes a
  report artefact
- a synchronous **probe** that retries with increasing `run_after` delays
  until a precondition is met, at most three attempts

Both pulse and summarise SHALL be enqueueable from the dashboard. Results
SHALL include enough payload for the dashboard to show a sample, report
path, or error.

#### Scenario: Submit a pulse run
- **WHEN** a user starts the pulse
- **THEN** a worker records a sample artefact under the demo directory
- **AND** the dashboard later shows a successful result for that generation

#### Scenario: Submit a summarise run
- **WHEN** a user submits the summarise task
- **THEN** a worker awaits that task, writes a report artefact from the
  recorded samples, and the dashboard shows a successful result

### Requirement: Immediate, delayed, and self-rescheduled enqueue

The demo SHALL allow immediate enqueue and enqueue with a future `run_after`.
A deferred task SHALL remain undispatched until its due time. The pulse SHALL
schedule its next generation by enqueueing itself with `run_after` unless
stop has been requested. Calendar schedules are out of scope.

#### Scenario: Immediate enqueue
- **WHEN** a user submits summarise without a delay
- **THEN** a worker may claim it as soon as it is pending

#### Scenario: Deferred enqueue
- **WHEN** a user submits summarise with a future `run_after`
- **THEN** the dashboard shows that work as scheduled until the due time
- **AND** a worker does not run it before that time

#### Scenario: Pulse reschedules itself
- **WHEN** a pulse generation completes successfully and stop is not requested
- **THEN** the worker enqueues the next generation with a future `run_after`
- **AND** the dashboard shows a new scheduled entry in that chain

#### Scenario: Pulse stop prevents the next generation
- **WHEN** a user stops the pulse
- **THEN** the in-flight generation may finish
- **AND** no further pulse generation is enqueued

#### Scenario: Pulse start while a chain is live
- **WHEN** a pulse chain is already running
- **THEN** a further Start does not enqueue generation 1
- **AND** Stop is required before a new chain

#### Scenario: Probe backs off with run_after
- **WHEN** the probe runs before its precondition is met and attempts
  remain
- **THEN** it records a retry and enqueues itself with a longer
  `run_after` than the previous attempt, up to a documented delay cap
  and at most three attempts

#### Scenario: Probe stops after three attempts
- **WHEN** the probe has run three times and the precondition is still
  unmet
- **THEN** it does not enqueue another attempt

### Requirement: Live board of queue lifecycle

The dashboard SHALL observe Redis queue lifecycle through django-queues'
async queue observer API. It SHALL NOT poll Redis from the browser. It SHALL
present entries in Scheduled and Done columns and update them without a
full-page refresh. Deferred entries SHALL show remaining wait. Pulse
generations SHALL be identifiable as a chain. Ready and running observer
states MAY be omitted from the board when they do not persist long enough
to display.

#### Scenario: Observe a successful run
- **WHEN** a submitted task is claimed and completes successfully
- **THEN** the dashboard shows the final result in Done

#### Scenario: Observe deferred work becoming due
- **WHEN** a deferred task's `run_after` is reached
- **THEN** the dashboard moves it from Scheduled to Done without a
  full-page refresh

#### Scenario: Observe a pulse chain
- **WHEN** two pulse generations have run and a third is waiting
- **THEN** the dashboard shows those generations as one chain rather than
  unrelated rows

### Requirement: Demo operating conventions

Startup SHALL match the neighbouring django-queues demos: Docker Compose for
Redis, `runserver` for the dashboard, and `runqueues` as a separate worker
process. The demo SHALL be database-free aside from Redis.

#### Scenario: Documented three-process workflow
- **WHEN** a developer starts Redis, the web server, and `runqueues` as
  documented
- **THEN** submitting a task from the dashboard produces worker execution and
  observer updates

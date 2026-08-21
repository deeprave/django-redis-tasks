## Purpose

Provide a runnable, self-contained Django application that visibly demonstrates
Redis-backed Django task submission, priority ordering, results, and lifecycle
updates without requiring any service other than local Redis.

## ADDED Requirements

### Requirement: Self-contained demo project

The repository SHALL provide a Django project under `demo/` with its own
dependency metadata and local Redis startup instructions. The demo SHALL use
the adjacent `redis_tasks` package as a dependency rather than duplicating its
backend implementation.

#### Scenario: Start the demonstration

- **WHEN** a developer follows the demo README's Redis, web-server, and worker
  commands
- **THEN** they can open a local dashboard backed by the configured Redis task
  queue

### Requirement: Task catalogue and priority submission

The dashboard SHALL present a catalogue of safe, low-cost tasks that inspect or
summarize files beneath the demo project directory. Each task submission SHALL
allow the user to select a valid Django task priority and SHALL display the
priority with the submitted task.

#### Scenario: Submit a catalogue task

- **WHEN** a user chooses a task and priority and submits it
- **THEN** the dashboard queues that task and shows it as queued with the
  selected priority

#### Scenario: Priority affects pending work

- **WHEN** multiple different catalogue tasks are queued before dispatch
- **THEN** the priority queue dispatches the highest-priority pending task
  first

### Requirement: Per-task single-flight submission

The dashboard SHALL prevent a catalogue task from being submitted again while
its previous submission is queued or running. It SHALL continue to allow
submissions of other catalogue tasks during that time.

#### Scenario: Disable an active task only

- **WHEN** a user submits one catalogue task
- **THEN** that task's submission control is disabled until it reaches a
  terminal state while controls for other task types remain available

#### Scenario: Re-enable after completion

- **WHEN** a catalogue task succeeds, fails, times out, or is cancelled
- **THEN** its submission control becomes available for a new run

### Requirement: Live task state and result presentation

The dashboard SHALL update task state without a full-page refresh and SHALL
show the final result or error for each submitted task. It SHALL represent
queued, running, and terminal lifecycle states.

#### Scenario: Observe a successful task

- **WHEN** a submitted task is dispatched and completes successfully
- **THEN** the browser receives live queued and running updates followed by the
  final result

#### Scenario: Observe a terminal failure

- **WHEN** a submitted task reaches a failed, timed-out, or cancelled state
- **THEN** the browser receives the terminal update and shows the recorded
  error while re-enabling that task type

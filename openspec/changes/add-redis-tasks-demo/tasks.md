## 1. Demo project foundation

- [x] 1.1 Create the independent `demo/` Django project (manage.py, settings,
      ASGI, dashboard app, editable `..` dependency, ignore rules, `demo/var/`
      for artefacts) and verify `uv sync` succeeds in `demo/`.
- [x] 1.2 Add Compose Redis on a localhost port that does not collide with
      django-queues `demo_aq`/`demo_pq`, plus `QUEUES`/`TASKS` using
      `RedisAsyncPriorityQueueJson`, `TaskQueueEntry`, `RedisTaskWorker`,
      `handle_task_entry`, and `RedisBackend`; verify Django checks pass.
- [x] 1.3 Add a README covering Compose Redis, `runserver`, and separate
      `runqueues`, matching django-queues demo tone; verify the three
      commands are documented.

## 2. Catalogue tasks

- [x] 2.1 Implement the synchronous pulse task: write a sample artefact,
      then enqueue the next generation with `run_after` unless stop is set;
      verify unit tests for one generation and for skip-on-stop.
- [x] 2.2 Implement the asynchronous summarise task that reads samples and
      writes a report artefact; verify a unit test enqueues it with
      `aenqueue`.
- [x] 2.3 Implement the probe task that retries with increasing `run_after`
      until a precondition is met, then stops; verify backoff and success
      paths.
- [x] 2.4 Add dashboard controls: pulse Start/Stop, summarise Run now and
      Run later, probe start; verify tests cover immediate enqueue,
      `enqueue(..., run_after=...)`, and the stop flag.

## 3. Observer dashboard

- [x] 3.1 Subscribe the dashboard process with `queue_observer` and keep a
      process-local projection of retained and live entries; verify tests
      map scheduled, ready, running, and terminal snapshots.
- [x] 3.2 Add an SSE endpoint that streams projection snapshots without the
      browser talking to Redis; verify framing tests.
- [x] 3.3 Add submit views: sync path uses `enqueue`, async path uses
      `aenqueue`; verify both return a queued task id.

## 4. Browser experience

- [x] 4.1 Build the dashboard template and JS with catalogue controls and a
      Scheduled / Done board driven by SSE snapshots; verify initial snapshot
      and live update handling.
- [x] 4.2 Show remaining wait for deferred entries, the pulse generation
      chain, and result/artefact or error in Done, without a full-page
      refresh; verify with a test or documented manual check.

## 5. Validation

- [x] 5.1 Run the demo tests plus repo ruff, ty, and pytest `-Werror`; verify
      they pass.
- [x] 5.2 Exercise Redis + `runserver` + `runqueues`: start/stop pulse,
      immediate and delayed summarise, and probe backoff appear and complete
      on the board with artefacts under `demo/var/`.
- [x] 5.3 Delete `openspec/changes/create-django-redis-tasks-demo` so only
      this demo change remains; verify `openspec list` no longer shows the
      old change as in-progress.

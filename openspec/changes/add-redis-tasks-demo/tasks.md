## 1. Demo project foundation

- [ ] 1.1 Create the independent `demo/` Django project (manage.py, settings,
      ASGI, dashboard app, editable `..` dependency, ignore rules) and verify
      `uv sync` succeeds in `demo/`.
- [ ] 1.2 Add Compose Redis on a localhost port that does not collide with
      django-queues `demo_aq`/`demo_pq`, plus `QUEUES`/`TASKS` using
      `RedisAsyncPriorityQueueJson`, `TaskQueueEntry`, `RedisTaskWorker`,
      `handle_task_entry`, and `RedisBackend`; verify Django checks pass.
- [ ] 1.3 Add a README covering Compose Redis, `runserver`, and separate
      `runqueues`, matching django-queues demo tone; verify the three
      commands are documented.

## 2. Catalogue tasks

- [ ] 2.1 Implement a synchronous Django task that returns a JSON-normalizable
      result and verify a unit test enqueues it through the task API.
- [ ] 2.2 Implement an asynchronous Django task (`async def`) and verify a
      unit test enqueues it with `aenqueue`.
- [ ] 2.3 Add dashboard controls for immediate enqueue and `run_after` delay;
      verify tests cover both `enqueue(..., run_after=...)` and the no-delay
      path.

## 3. Observer dashboard

- [ ] 3.1 Subscribe the dashboard process with `queue_observer` and keep a
      process-local projection of retained and live entries; verify tests
      map queued, running, and terminal snapshots.
- [ ] 3.2 Add an SSE endpoint that streams projection snapshots without the
      browser talking to Redis; verify framing tests.
- [ ] 3.3 Add submit views: sync path uses `enqueue`, async path uses
      `aenqueue`; verify both return a queued task id.

## 4. Browser experience

- [ ] 4.1 Build the dashboard template and JS that show catalogue cards,
      delay control, lifecycle state, and result/error from SSE snapshots;
      verify initial snapshot and live update handling.
- [ ] 4.2 Show deferred tasks as waiting until due, then running, without a
      full-page refresh; verify with a test or documented manual check.

## 5. Validation and supersede old change

- [ ] 5.1 Run the demo tests plus repo ruff, ty, and pytest `-Werror`; verify
      they pass.
- [ ] 5.2 Exercise Redis + `runserver` + `runqueues`: sync, async, and
      delayed tasks appear and complete on the dashboard.
- [ ] 5.3 Archive or delete `openspec/changes/create-django-redis-tasks-demo`
      so only this demo change remains; verify `openspec list` no longer
      shows the old change as in-progress.

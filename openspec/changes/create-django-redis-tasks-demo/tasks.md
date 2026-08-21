## 1. Demo project foundation

- [ ] 1.1 Create the independent `demo/` Django project, dashboard app, local
  editable dependency configuration, and repository-appropriate ignore rules.
- [ ] 1.2 Add Docker Compose Redis, Django settings, and queue/task settings
  using `RedisAsyncPriorityQueueJson`, `TaskQueueEntry`, and
  `RedisTaskWorker`.
- [ ] 1.3 Add a concise demo README covering Redis, web-server, and separate
  `runqueues` worker startup.

## 2. Catalogue tasks and submission

- [ ] 2.1 Implement bounded asynchronous directory inventory,
  file-extension-summary, and source-text-search tasks that return
  JSON-normalizable results from the demo directory only.
- [ ] 2.2 Define task catalogue metadata, valid priority choices, and payload
  metadata that identifies the logical catalogue task.
- [ ] 2.3 Implement the server-side per-task single-flight admission gate and
  task submission endpoint, including a conflict response for duplicate active
  submissions.
- [ ] 2.4 Add unit tests for task directory boundaries, result shapes,
  priority forwarding, and per-task admission behavior.

## 3. Live dashboard updates

- [ ] 3.1 Implement an observer-backed, lock-protected projection of retained
  and live queue entries, including active-task indexing and terminal cleanup.
- [ ] 3.2 Add an SSE endpoint that streams projection snapshots and keepalive
  frames without polling Redis directly from the dashboard.
- [ ] 3.3 Add views and tests for dashboard rendering, submission responses,
  projection lifecycle mapping, and SSE framing.

## 4. Browser experience

- [ ] 4.1 Build the dashboard template and lightweight JavaScript that renders
  task cards, priority controls, selected priority, lifecycle state, worker
  attempts, result, and error.
- [ ] 4.2 Disable only the submitted task's card while queued or running and
  re-enable it on every terminal observer update.
- [ ] 4.3 Verify the page handles initial retained-entry snapshots, live
  updates, and reconnects without requiring a full-page refresh.

## 5. Validation and documentation

- [ ] 5.1 Run the demo's test suite and the repository's required formatting,
  linting, type-checking, and warning-as-error test checks.
- [ ] 5.2 Exercise the documented local workflow with Redis, the Django web
  server, and `runqueues`; verify multiple queued catalogue tasks demonstrate
  selected priority ordering and live terminal results.

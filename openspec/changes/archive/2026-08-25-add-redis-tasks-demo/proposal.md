## Why

The library has a working Django Tasks Redis backend, including deferred
`run_after` work, but no small application a user can run to see it. Unit
tests prove contracts; they do not show enqueue, dispatch, delay, live queue
observation, or work that leaves a visible artefact. The neighbouring
`django-queues` demos already define the process layout.

## What Changes

- Add a self-contained Django project under `demo/` that consumes this package
  as an editable dependency, following `demo_aq` / `demo_pq` in
  `../django-queues` (database-free, Docker Compose Redis, `runserver` plus
  `runqueues`, observer-backed dashboard, SSE).
- Demonstrate the Django Tasks API through this backend with a small catalogue
  of **meaningful** work: a self-rescheduling pulse that records samples, a
  one-shot summariser of those samples (immediate and delayed), and a flaky
  probe that backs off with `run_after`.
- Self-reschedule by enqueueing the next run with `run_after`, not by calendar
  schedules (`add-schedule-support` stays out of scope). The dashboard can
  start and stop the pulse so it cannot run away.
- Show a live board of Scheduled and Done, including a pulse generation
  chain and remaining wait for deferred work.
- Observe Redis-backed queue lifecycle through django-queues'
  `queue_observer` (the public API over Redis `aobserve`), not by polling
  Redis from the browser.
- Document local Redis, web, and worker startup in the same style as the
  django-queues demos.
- The superseded `create-django-redis-tasks-demo` change is already deleted.

## Capabilities

### New Capabilities

- `redis-tasks-demo`: A runnable Django demo that submits meaningful sync and
  async tasks, including immediate, delayed, and self-rescheduled `run_after`
  work, and shows Redis queue lifecycle on a live dashboard.

### Modified Capabilities

None.

## Impact

- New `demo/` tree (pyproject, Compose Redis, Django project, dashboard,
  demo-local artefacts under `demo/var/`, README). No change to the library's
  public task API.
- Demo depends on this package and `django-queues[redis]`; Redis is the only
  extra service.

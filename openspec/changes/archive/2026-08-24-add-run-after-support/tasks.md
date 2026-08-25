## 1. django-queues 1.2.0 dependency and Redis runtime

- [x] 1.1 Raise `django-queues[redis]` to `>=1.2.0,<2.0.0` and refresh the lockfile.
- [x] 1.2 Deploy the django-queues Redis Function library in Redis test fixtures
  (`redis_lua_lib --deploy` against the testcontainers instance) so 1.2.0
  queues can start.
- [x] 1.3 Confirm test Redis is 7+ and queue aliases remain `[A-Za-z0-9_-]`.

## 2. Redis task backend

- [x] 2.1 Set `RedisBackend.supports_defer = True`.
- [x] 2.2 Add helpers to normalize `Task.run_after` using Django timezone
  settings and serialize/deserialize it in the task payload.
- [x] 2.3 Pass `available_at=ClockTime.from_datetime(...)` on sync and async
  enqueue when `run_after` is set; omit it otherwise; preserve `run_after` when
  reconstructing task metadata.

## 3. Verification

- [x] 3.1 Add unit tests for `supports_defer`, payload round-tripping, aware
  and naive timezone handling, and immediate/past due times.
- [x] 3.2 Add testcontainers integration tests proving a future task is not
  dispatched early, remains `READY` without attempts, and is promoted and
  dispatched after its due time.
- [x] 3.3 Add priority integration tests for due promotion, priority ordering,
  equal-priority FIFO ordering, and a queue containing only future work.
- [x] 3.4 Run the repository quality gates: Ruff check/format, ty, pytest with
  `-Walways -Werror`, osvcheck, validate-pyproject, and strict OpenSpec
  validation.

## 4. Documentation

- [x] 4.1 Replace the README's `run_after` limitation with timezone,
  Redis-time, worker-claim waiting, Redis 7+, Function-library deploy, and
  pre-1.2.0 key incompatibility.
- [x] 4.2 Add a changelog entry describing durable deferred-task support and
  the django-queues 1.2.0 floor.

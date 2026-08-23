## Why

`django.tasks.Task.run_after` is part of Django's task contract, but the Redis
backend currently declares `supports_defer = False`. django-queues 1.1.0 added
durable `available_at` scheduling; 1.2.0 is the adopted dependency. This package
must map Django's due time onto that queue API instead of rejecting deferred
tasks.

## What Changes

- Raise the django-queues pin to `>=1.2.0,<2.0.0`.
- Add durable `run_after` support to `RedisBackend` and set
  `supports_defer = True`.
- Normalize `run_after` to UTC and pass it to tracked
  `enqueue()`/`aenqueue()` as `available_at=ClockTime`; omit the argument when
  `run_after` is unset. Past or omitted instants stay immediately eligible
  (queue behaviour).
- Persist `run_after` in the Django task payload for result reconstruction.
- Deploy django-queues' Redis Function library in tests and document Redis 7+,
  Function deploy, and incompatible pre-1.2.0 Redis queue keys.
- Document deferred-task timing and worker-capacity behaviour.

## Capabilities

### New Capabilities

- `deferred-django-tasks`: Durable earliest-execution scheduling for Django
  tasks backed by a configured django-queues Redis queue's `available_at`.

### Modified Capabilities

None.

## Impact

- `redis_tasks.backend`, task payload/result mapping, tests, README, changelog,
  and django-queues minimum version.
- No delay API is added in this package. django-queues owns scheduled index,
  due promotion, claim, and Function-library runtime. Existing non-deferred
  tasks keep their current enqueue path aside from the 1.2.0 Redis runtime.

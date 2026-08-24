# Changelog

## v1.0.0 - 2026-08-24

- Support Django `run_after` deferred tasks by passing UTC `available_at` through django-queues 1.2.0.
- Require Redis 7+ and a deployed django-queues Redis Function library.

## v1.0.0a1

- Add the Django 6 `django.tasks` Redis backend implementation, powered by `django-queues`.
- Support Redis-backed priority queues, `takes_context` tasks, and worker IDs.
- Document configuration, worker operation, and the remaining task-backend limitation.

import os

import django_queue
import pytest

from redis_tasks.backend import RedisBackend
from tests.django_src import DjangoTasksSourceError, register_django_tasks_collection


def _slow_tests_enabled():
    return os.getenv("SLOW_TESTS") in ("true", "1", "enabled")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: mark test as slow (skipped unless SLOW_TESTS=true/1/enabled)"
    )
    pytest.mark.slow = pytest.mark.skipif(
        not _slow_tests_enabled(),
        reason="Test skipped because SLOW_TESTS environment variable not set to true, 1 or enabled",
    )
    try:
        register_django_tasks_collection(config)
    except DjangoTasksSourceError as exc:
        raise pytest.UsageError(str(exc)) from exc


@pytest.fixture
def task_queue(redis_url):
    queue = django_queue.QueueRegistry(
        {
            "default": {
                "BACKEND": "django_queue.backends.redis.RedisAsyncPriorityQueueJson",
                "LOCATION": redis_url,
                "ENTRY_CLASS": "redis_tasks.entries.TaskQueueEntry",
                "WORKER": "redis_tasks.worker.RedisTaskWorker",
            }
        }
    )["default"]
    queue._run_synchronously(queue._provider.aclear_records)
    try:
        yield queue
    finally:
        queue._run_synchronously(queue._provider.aclear_records)
        queue.close()


@pytest.fixture
def redis_backend(task_queue, monkeypatch):
    backend = RedisBackend(alias="default", params={"QUEUES": ["default", "alternate"]})
    monkeypatch.setattr(backend, "_resolve_queue", lambda: task_queue)
    return backend

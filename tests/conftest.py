from collections.abc import Iterator

import django_queue
import pytest
from django.conf import settings
from testcontainers.community.redis import RedisContainer

from redis_tasks.backend import RedisBackend


def pytest_configure():
    if not settings.configured:
        settings.configure(
            USE_TZ=True,
            TASKS={
                "default": {
                    "BACKEND": "redis_tasks.backend.RedisBackend",
                    "QUEUES": ["default", "alternate"],
                }
            },
            QUEUES={
                "default": {
                    "BACKEND": "django_queue.backends.redis.RedisAsyncPriorityQueueJson",
                    "LOCATION": "redis://localhost:6379/0",
                    "ENTRY_CLASS": "redis_tasks.entries.TaskQueueEntry",
                    "WORKER": "redis_tasks.worker.RedisTaskWorker",
                }
            },
        )


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:latest") as redis_container:
        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


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

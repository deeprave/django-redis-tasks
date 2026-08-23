import os
from collections.abc import Iterator

import django_queue
import pytest
import redis
from django.conf import settings
from django_queue.backends.redis.functions import load_function_library
from testcontainers.community.redis import RedisContainer

from redis_tasks.backend import RedisBackend

_REDIS_IMAGE = "redis:7-alpine"


def _deploy_django_queues_functions(redis_url: str) -> None:
    """Load the bundled Function library, equivalent to ``redis_lua_lib --deploy``."""
    library = load_function_library()
    client = redis.Redis.from_url(redis_url)
    try:
        version = client.info("server")["redis_version"]
        major = int(str(version).split(".", 1)[0])
        if major < 7:
            raise RuntimeError(f"django-queues 1.2.0 requires Redis 7+, not {version}")
        client.function_load(library.source.decode("utf-8"), replace=True)
    finally:
        client.close()


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
    with RedisContainer(_REDIS_IMAGE) as redis_container:
        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        redis_url = f"redis://{host}:{port}/0"
        _deploy_django_queues_functions(redis_url)
        yield redis_url


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

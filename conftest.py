from collections.abc import Iterator

import django_queue
import pytest
import redis
from django.conf import settings
from django_queue.backends.redis.functions import load_function_library
from testcontainers.community.redis import RedisContainer

pytest_plugins = ["tests.django_src"]

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


def _point_django_queues_at(redis_url: str) -> None:
    settings.QUEUES["default"]["LOCATION"] = redis_url
    queue_settings = django_queue.queues.settings
    queue_settings["default"]["LOCATION"] = redis_url
    django_queue.queues.close_all()


def _clear_default_task_queue() -> None:
    queue = django_queue.queues["default"]
    queue._run_synchronously(queue._provider.aclear_records)


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    """Session Redis for both package tests and Django tests collected from cache."""
    with RedisContainer(_REDIS_IMAGE) as redis_container:
        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        redis_url = f"redis://{host}:{port}/0"
        _deploy_django_queues_functions(redis_url)
        _point_django_queues_at(redis_url)
        yield redis_url


@pytest.fixture(autouse=True)
def django_task_test_isolation(request):
    module_name = getattr(request.module, "__name__", "")
    if module_name != "tasks.test_tasks":
        yield
        return
    request.getfixturevalue("redis_url")
    _clear_default_task_queue()
    try:
        yield
    finally:
        _clear_default_task_queue()

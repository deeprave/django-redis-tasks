import redis
import pytest
from testcontainers.redis import RedisContainer

from redis_tasks.taskqueue import RedisTaskQueue
from redis_tasks.backend import RedisBackend


@pytest.fixture(scope="module")
def redis_client() -> redis.Redis:
    with RedisContainer() as redis_container:
        yield redis_container.get_client()


@pytest.fixture
def redis_task_queue(redis_client):
    return RedisTaskQueue(location=redis_client, queue_name="test_queue", ttl=600, encoding="utf-8")


@pytest.fixture
def redis_backend(redis_client):
    return RedisBackend(alias="default", params=dict(location=redis_client, queue_name="test_queue", ttl=600, encoding="utf-8"))

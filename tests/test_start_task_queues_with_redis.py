import pytest
import asyncio
from redis_tasks import start_task_queues


@pytest.mark.asyncio
async def test_start_task_queues_with_redis(redis_backend):
    # Start processing queues
    task = asyncio.create_task(start_task_queues())
    await asyncio.sleep(0.5)

    # Verify the backend is registered correctly and processing starts
    assert redis_backend.queue  # Queue should be initialized
    assert redis_backend.queue.queue_name == "test_queue"
    assert redis_backend.queue.redis.connection_pool # Actual Redis connected

    # Clean up: stop async loop
    task.cancel()
    await task
    assert task.done()


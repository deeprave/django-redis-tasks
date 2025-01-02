from datetime import timezone

import pytest
import json
import datetime
import asyncio
from redis_tasks.taskqueue import TaskState, Namespace


def sample_function(*_args, **kwargs):
    assert kwargs["testing"]
    return "This is the result"


@pytest.mark.asyncio
async def test_redis_property(redis_task_queue, redis_client):
    assert redis_task_queue.redis == redis_client


@pytest.mark.asyncio
async def test_default_ttl(redis_task_queue):
    assert redis_task_queue.default_ttl == 600


@pytest.mark.asyncio
async def test_queue_name(redis_task_queue):
    assert redis_task_queue.queue_name == "test_queue"


@pytest.mark.asyncio
async def test_encoding(redis_task_queue):
    assert redis_task_queue.encoding == "utf-8"


@pytest.mark.asyncio
async def test_task_key(redis_task_queue):
    task_key = "test_task"
    expected_key = "test_queue:task:test_task"
    assert redis_task_queue.task_key(task_key) == expected_key


@pytest.mark.asyncio
async def test_state_queue(redis_task_queue):
    state = TaskState.READY
    expected_queue = "test_queue:ready"
    assert redis_task_queue.state_queue(state) == expected_queue


@pytest.mark.asyncio
async def test_encode(redis_task_queue):
    data = Namespace(key="value")
    encoded_data = redis_task_queue.encode_data(data)
    dumped_data = json.dumps(data.__dict__).encode("utf-8")
    assert encoded_data == dumped_data


@pytest.mark.asyncio
async def test_decode(redis_task_queue):
    data = Namespace(key="value")
    encoded_data = json.dumps(data.__dict__).encode("utf-8")
    decoded_data = redis_task_queue.decode_data(encoded_data)
    assert decoded_data.__dict__ == {"key": "value"}


@pytest.mark.asyncio
async def test_add_task(redis_task_queue, redis_client):
    task = redis_task_queue.add_task(sample_function, priority=0, testing=True)

    assert isinstance(task, Namespace)
    task_key = task.task_key

    task_store_key = redis_task_queue.task_key(task_key)
    task_data_stored = redis_client.get(task_store_key)
    assert task_data_stored is not None

    decoded_task = redis_task_queue.decode_data(task_data_stored)
    assert decoded_task.task_key == task_key
    assert decoded_task.state == TaskState.READY.value

    ready_queue = redis_task_queue.state_queue(TaskState.READY)
    queue_items = redis_client.zrange(ready_queue, 0, -1)
    assert task_key.encode() in queue_items

    redis_task_queue.clear_tasks()


@pytest.mark.asyncio
async def test_get_next_task(redis_task_queue, redis_client):
    task = redis_task_queue.add_task(sample_function, priority=1)
    task_key = task.task_key

    next_task = await redis_task_queue.get_next_task()
    assert next_task is not None
    assert next_task.task_key == task_key
    assert next_task.state == TaskState.PROCESSING.value

    ready_queue = redis_task_queue.state_queue(TaskState.READY)
    processing_queue = redis_task_queue.state_queue(TaskState.PROCESSING)

    assert redis_client.zrange(ready_queue, 0, -1) == []
    queue_items = redis_client.zrange(processing_queue, 0, -1)
    assert task_key.encode() in queue_items

    redis_task_queue.clear_tasks()


@pytest.mark.asyncio
async def test_task_dispatch(redis_task_queue, redis_client):
    task = redis_task_queue.add_task(sample_function, priority=0, testing=True)
    task_key = task.task_key

    assert isinstance(task_key, str)

    task_store_key = redis_task_queue.task_key(task_key)
    task_data_stored = redis_client.get(task_store_key)
    assert task_data_stored is not None

    decoded_task = redis_task_queue.decode_data(task_data_stored)
    assert decoded_task.task_key == task_key
    assert decoded_task.state == TaskState.READY.value
    assert decoded_task.enqueued_at is not None

    await redis_task_queue.dispatch()

    ready_queue = redis_task_queue.state_queue(TaskState.READY)
    queue_items = redis_client.zrange(ready_queue, 0, -1)
    assert not queue_items

    redis_task_queue.clear_tasks()


@pytest.mark.asyncio
async def test_task_dispatch_exception(redis_task_queue, redis_client):
    task = redis_task_queue.add_task(sample_function, priority=0, testing=False)
    task_key = task.task_key

    assert isinstance(task_key, str)

    task_store_key = redis_task_queue.task_key(task_key)
    task_data_stored = redis_client.get(task_store_key)
    assert task_data_stored is not None

    decoded_task = redis_task_queue.decode_data(task_data_stored)
    assert decoded_task.task_key == task_key
    assert decoded_task.state == TaskState.READY.value

    await redis_task_queue.dispatch()

    ready_queue = redis_task_queue.state_queue(TaskState.READY)
    queue_items = redis_client.zrange(ready_queue, 0, -1)
    assert not queue_items

    redis_task_queue.clear_tasks()


@pytest.mark.asyncio
async def test_complete_task(redis_task_queue, redis_client):
    task = redis_task_queue.add_task(sample_function, priority=5, testing=True)
    task_key = task.task_key

    assert await redis_task_queue.complete_task(task_key)

    task_store_key = redis_task_queue.task_key(task_key)
    stored_task = redis_task_queue.decode_data(redis_client.get(task_store_key))
    assert stored_task.state == TaskState.COMPLETED.value

    redis_task_queue.clear_tasks()


@pytest.mark.asyncio
async def test_fail_task(redis_task_queue, redis_client):
    task = redis_task_queue.add_task(sample_function, priority=5)
    task_key = task.task_key
    exception = RuntimeError("An error occurred")

    assert await redis_task_queue.complete_task(task_key, exc=exception)

    task_store_key = redis_task_queue.task_key(task_key)
    stored_task = redis_task_queue.decode_data(redis_client.get(task_store_key))
    assert stored_task.state == TaskState.FAILED.value
    assert stored_task.exception_class == RuntimeError.__name__
    assert stored_task.traceback == f"RuntimeError: {exception}\n"

    redis_task_queue.clear_tasks()


@pytest.mark.asyncio
async def test_get_task_status_async(redis_task_queue, redis_client):
    task = redis_task_queue.add_task(sample_function, priority=5)
    task_key = task.task_key

    status = await redis_task_queue.get_task_status_async(task_key)
    assert status is not None
    assert status.task_key == task_key
    assert status.state == TaskState.READY.value

    redis_task_queue.clear_tasks()


def test_get_task_status(redis_task_queue, redis_client):
    task = redis_task_queue.add_task(sample_function, priority=5)
    task_key = task.task_key

    status = redis_task_queue.get_task_status(task_key)
    assert status is not None
    assert status.task_key == task_key
    assert status.state == TaskState.READY.value

    redis_task_queue.clear_tasks()


@pytest.mark.asyncio
async def test_add_task_with_run_after(redis_task_queue, redis_client):
    # Schedule a task to start 2 seconds in the future
    now = datetime.datetime.now(timezone.utc)
    run_after_time = now + datetime.timedelta(seconds=2)
    task = redis_task_queue.add_task(sample_function, priority=0, run_after=run_after_time, testing=True)
    task_key = task.task_key

    waiting_queue = redis_task_queue.state_queue(TaskState.WAITING)
    ready_queue = redis_task_queue.state_queue(TaskState.READY)

    # Verify the task is in the waiting queue
    queue_items = redis_client.zrange(waiting_queue, 0, -1)
    assert task_key.encode() in queue_items

    # Verify the task is not in the ready queue
    queue_items = redis_client.zrange(ready_queue, 0, -1)
    assert task_key.encode() not in queue_items

    # Wait for sufficient time to transition the task to the ready queue
    await asyncio.sleep(2.0)

    # Dispatch to complete the task
    await redis_task_queue.dispatch()

    # Verify the task is no longer in the waiting queue
    queue_items = redis_client.zrange(waiting_queue, 0, -1)
    assert not queue_items

    # Verify the task state is COMPLETED
    task_store_key = redis_task_queue.task_key(task_key)
    stored_task = redis_task_queue.decode_data(redis_client.get(task_store_key))
    assert stored_task.state == TaskState.COMPLETED.value

    task = await redis_task_queue.get_task_status_async(task_key)
    assert task.state == TaskState.COMPLETED.value
    assert task.started_at is not None
    assert task.finished_at is not None
    assert task.return_value == "This is the result"

    redis_task_queue.clear_tasks()

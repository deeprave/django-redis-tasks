# File: test_async_tasks.py

import asyncio

import contextlib
import pytest

from redis_tasks.runqueue import start_task_queues

task_calls = []

# Define a global task function
def sample_task(*args, **kwargs):
    task_calls.append({"args": args, "kwargs": kwargs})
    if "test_exception" in kwargs:
        raise ValueError("Test exception")
    return f"Processed {args}, {kwargs}"


@pytest.mark.asyncio
async def test_start_queue_task(redis_task_queue):
    task_calls.clear()

    # Add a runnable task to the queue
    successful_task = redis_task_queue.add_task(sample_task, "test_arg", key="value")
    task_key = successful_task.task_key

    # Start the queue processing
    task_runner = asyncio.create_task(start_task_queues())

    # Allow loop to process the queue for a moment
    await asyncio.sleep(1.0)

    successful_task = await redis_task_queue.get_task_status_async(task_key)
    assert successful_task.state == "completed"
    assert successful_task.args == ["test_arg"]
    assert successful_task.kwargs == {"key": "value"}
    assert successful_task.return_value == "Processed ('test_arg',), {'key': 'value'}"

    assert len(task_calls) == 1  # Ensure it was called exactly once
    assert task_calls[0]["args"] == ("test_arg",)
    assert task_calls[0]["kwargs"] == {"key": "value"}

    # Validate that the task was processed
    assert await redis_task_queue.dispatch() is False  # No task should be left to process

    failed_task = redis_task_queue.add_task(sample_task, "test_arg", key="value", test_exception=True)
    task_key = failed_task.task_key

    # Allow loop to process the queue for a moment
    await asyncio.sleep(2.5)

    failed_task = await redis_task_queue.get_task_status_async(task_key)
    assert failed_task.state == "failed"
    assert failed_task.args == ["test_arg"]
    assert failed_task.kwargs == {"key": "value", "test_exception": True}
    assert failed_task.exception_class == "ValueError"
    assert failed_task.traceback is not None

    assert len(task_calls) == 2  # Ensure it was called exactly once
    assert task_calls[1]["args"] == ("test_arg",)
    assert task_calls[1]["kwargs"] == {"key": "value", "test_exception": True}

    assert await redis_task_queue.dispatch() is False  # No task should be left to process

    # Cancel the processing loop
    task_runner.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task_runner

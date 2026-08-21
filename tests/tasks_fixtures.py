"""Module-level task functions used as enqueue targets in tests."""

import asyncio

from django.tasks import task


def add(a, b):
    return a + b


async def async_add(a, b):
    return a + b


def always_fails():
    raise ValueError("deliberate failure")


def returns_bytes():
    return b"queued result"


async def async_always_fails():
    raise ValueError("deliberate async failure")


async def raises_cancelled_error():
    raise asyncio.CancelledError("task cancellation")


async def self_cancels():
    current_task = asyncio.current_task()
    assert current_task is not None
    current_task.cancel()
    await asyncio.sleep(0)


@task()
def decorated_add(a, b):
    return a + b


@task()
async def decorated_async_add(a, b):
    return a + b


@task(takes_context=True)
def add_with_context(context, a, b):
    return {"result_id": context.task_result.id, "value": a + b}


@task(takes_context=True)
def context_timestamps(context):
    return {
        "started_at": context.task_result.started_at.isoformat(),
        "last_attempted_at": context.task_result.last_attempted_at.isoformat(),
    }

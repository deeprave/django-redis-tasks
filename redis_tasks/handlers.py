import asyncio
from typing import Any, cast

from django.tasks.base import TaskContext, TaskResultStatus
from django.tasks.signals import task_started
from django.utils.json import normalize_json
from django_queue.entries import QueueEntry

from redis_tasks.backend import task_from_payload, task_result_from_entry
from redis_tasks.entries import TaskQueueEntry


async def handle_task_entry(entry: QueueEntry) -> Any:
    payload = entry.payload
    task = task_from_payload(payload, payload.get("backend", entry.queue))
    result = task_result_from_entry(task, cast(TaskQueueEntry, entry), task.backend)
    args, kwargs = payload["args"], payload["kwargs"]
    backend_type = type(task.get_backend())
    object.__setattr__(result, "status", TaskResultStatus.RUNNING)
    await task_started.asend(backend_type, task_result=result)

    async def call_task() -> Any:
        if task.takes_context:
            return await task.acall(TaskContext(task_result=result), *args, **kwargs)
        return await task.acall(*args, **kwargs)

    try:
        value = await asyncio.create_task(call_task())
    except asyncio.CancelledError as exc:
        current_task = asyncio.current_task()
        if current_task is not None and current_task.cancelling():
            raise
        raise RuntimeError("Task function raised asyncio.CancelledError") from exc
    return normalize_json(value)

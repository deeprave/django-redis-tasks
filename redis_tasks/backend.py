import builtins
import uuid
from typing import Any, cast

import django_queue
from django.core.exceptions import ImproperlyConfigured
from django.tasks.backends.base import BaseTaskBackend
from django.tasks.base import Task, TaskError, TaskResult, TaskResultStatus
from django.tasks.exceptions import TaskResultDoesNotExist
from django.tasks.signals import task_enqueued
from django.utils.json import normalize_json
from django.utils.module_loading import import_string
from django_queue.backends.base import AsyncQueue
from django_queue.backends.exceptions import QueueEntryNotFoundError
from django_queue.backends.redis.redisqueue import RedisAsyncQueue
from django_queue.entries import QueueEntryStatus

from redis_tasks.entries import TaskQueueEntry

_STATUS_MAP = {
    QueueEntryStatus.QUEUED: TaskResultStatus.READY,
    QueueEntryStatus.RUNNING: TaskResultStatus.RUNNING,
    QueueEntryStatus.SUCCEEDED: TaskResultStatus.SUCCESSFUL,
    QueueEntryStatus.FAILED: TaskResultStatus.FAILED,
    QueueEntryStatus.TIMEOUT: TaskResultStatus.FAILED,
    QueueEntryStatus.CANCELLED: TaskResultStatus.FAILED,
}


def task_from_payload(
    payload: dict[str, Any], backend_alias: str, *, allow_missing: bool = False
) -> Task:
    try:
        imported = import_string(payload["func"])
    except ImportError, AttributeError:
        if not allow_missing:
            raise
        module_name, _, function_name = payload["func"].rpartition(".")

        if payload.get("takes_context", False):

            def unavailable_task(context: Any, *args: Any, **kwargs: Any) -> None:
                raise ImportError(
                    f"Task function {payload['func']!r} is no longer importable"
                )

        else:

            def unavailable_task(*args: Any, **kwargs: Any) -> None:
                raise ImportError(
                    f"Task function {payload['func']!r} is no longer importable"
                )

        unavailable_task.__module__ = module_name
        unavailable_task.__name__ = function_name
        unavailable_task.__qualname__ = function_name
        imported = unavailable_task
    return Task(
        func=imported.func if isinstance(imported, Task) else imported,
        priority=payload.get("priority", 0),
        backend=payload.get("backend", backend_alias),
        queue_name=payload.get("queue_name", "default"),
        takes_context=payload.get("takes_context", False),
    )


def task_result_from_entry(
    task: Task, entry: TaskQueueEntry, backend_alias: str
) -> TaskResult:
    status = _STATUS_MAP[entry.status]
    if entry.error is not None:
        exception_name = entry.error["type"]
        exception_class_path = (
            f"builtins.{exception_name}"
            if isinstance(getattr(builtins, exception_name, None), type)
            and issubclass(getattr(builtins, exception_name), BaseException)
            else "builtins.Exception"
        )
        errors = [
            TaskError(
                exception_class_path=exception_class_path,
                traceback=entry.error["message"],
            )
        ]
    elif entry.status == QueueEntryStatus.TIMEOUT:
        errors = [
            TaskError(
                exception_class_path="builtins.TimeoutError",
                traceback="Task execution timed out.",
            )
        ]
    elif entry.status == QueueEntryStatus.CANCELLED:
        errors = [
            TaskError(
                exception_class_path="asyncio.exceptions.CancelledError",
                traceback="Task execution was cancelled.",
            )
        ]
    else:
        errors = []
    result = TaskResult(
        task=task,
        id=str(entry.id),
        status=status,
        enqueued_at=entry.queued_at.to_datetime() if entry.queued_at else None,
        started_at=entry.dispatched_at.to_datetime() if entry.dispatched_at else None,
        finished_at=entry.finished_at.to_datetime() if entry.finished_at else None,
        last_attempted_at=entry.dispatched_at.to_datetime()
        if entry.dispatched_at
        else None,
        args=entry.payload.get("args", []),
        kwargs=entry.payload.get("kwargs", {}),
        backend=backend_alias,
        errors=errors,
        worker_ids=entry.worker_ids,
    )
    if status == TaskResultStatus.SUCCESSFUL:
        object.__setattr__(result, "_return_value", entry.result)
    return result


def task_payload(task: Task, args: list, kwargs: dict) -> dict[str, Any]:
    return {
        "func": task.module_path,
        "args": normalize_json(list(args)),
        "kwargs": normalize_json(kwargs),
        "takes_context": task.takes_context,
        "backend": task.backend,
        "queue_name": task.queue_name,
        "priority": task.priority,
    }


class RedisBackend(BaseTaskBackend):
    supports_async_task = True
    supports_get_result = True
    supports_defer = False
    supports_priority = True

    def __init__(self, alias: str, params: dict[str, Any]) -> None:
        self._queue_alias = (params.get("OPTIONS") or {}).get("queue_alias", alias)
        super().__init__(alias=alias, params=params)
        if not isinstance(self._queue_alias, str) or not self._queue_alias:
            raise ImproperlyConfigured(
                "Redis task backend OPTIONS.queue_alias must be a non-empty string."
            )
        if self._queue_alias not in django_queue.queues.settings:
            raise ImproperlyConfigured(
                f"Redis task backend queue_alias {self._queue_alias!r} is not "
                "configured in QUEUES."
            )
        try:
            queue_backend = import_string(
                django_queue.queues.settings[self._queue_alias]["BACKEND"]
            )
            is_redis_queue = issubclass(queue_backend, RedisAsyncQueue)
        except (ImportError, AttributeError, TypeError) as exc:
            raise ImproperlyConfigured(
                f"Redis task backend queue_alias {self._queue_alias!r} must use a "
                "RedisAsyncQueue-compatible backend."
            ) from exc
        if not is_redis_queue:
            raise ImproperlyConfigured(
                f"Redis task backend queue_alias {self._queue_alias!r} must use a "
                "RedisAsyncQueue-compatible backend."
            )
        entry_class = django_queue.queues.settings[self._queue_alias].get("ENTRY_CLASS")
        if isinstance(entry_class, str):
            entry_class = import_string(entry_class)
        if not isinstance(entry_class, type) or not issubclass(
            entry_class, TaskQueueEntry
        ):
            raise ImproperlyConfigured(
                f"Redis task backend queue_alias {self._queue_alias!r} must "
                "configure an ENTRY_CLASS compatible with TaskQueueEntry."
            )
        worker_class = django_queue.queues.settings[self._queue_alias].get("WORKER")
        if isinstance(worker_class, str):
            worker_class = import_string(worker_class)
        from redis_tasks.worker import RedisTaskWorker

        if not isinstance(worker_class, type) or not issubclass(
            worker_class, RedisTaskWorker
        ):
            raise ImproperlyConfigured(
                f"Redis task backend queue_alias {self._queue_alias!r} must "
                "configure a WORKER compatible with RedisTaskWorker."
            )

    def _resolve_queue(self) -> AsyncQueue:
        return django_queue.queues[self._queue_alias]

    def enqueue(self, task: Task, args: list, kwargs: dict) -> TaskResult:
        self.validate_task(task)
        payload = task_payload(task, args, kwargs)
        queue = self._resolve_queue()
        entry_id = queue.enqueue(payload, priority=task.priority)
        entry = queue.find(entry_id)
        result = task_result_from_entry(task, cast(TaskQueueEntry, entry), self.alias)
        task_enqueued.send(type(self), task_result=result)
        return result

    async def aenqueue(self, task: Task, args: list, kwargs: dict) -> TaskResult:
        self.validate_task(task)
        payload = task_payload(task, args, kwargs)
        queue = self._resolve_queue()
        entry_id = await queue.aenqueue(payload, priority=task.priority)
        entry = await queue.afind(entry_id)
        result = task_result_from_entry(task, cast(TaskQueueEntry, entry), self.alias)
        await task_enqueued.asend(type(self), task_result=result)
        return result

    def get_result(self, result_id: str) -> TaskResult:
        try:
            entry_id = uuid.UUID(result_id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise TaskResultDoesNotExist(result_id) from exc
        try:
            entry = self._resolve_queue().find(entry_id)
        except QueueEntryNotFoundError as exc:
            raise TaskResultDoesNotExist(result_id) from exc
        task = task_from_payload(entry.payload, self.alias, allow_missing=True)
        return task_result_from_entry(task, cast(TaskQueueEntry, entry), self.alias)

    async def aget_result(self, result_id: str) -> TaskResult:
        try:
            entry_id = uuid.UUID(result_id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise TaskResultDoesNotExist(result_id) from exc
        try:
            entry = await self._resolve_queue().afind(entry_id)
        except QueueEntryNotFoundError as exc:
            raise TaskResultDoesNotExist(result_id) from exc
        task = task_from_payload(entry.payload, self.alias, allow_missing=True)
        return task_result_from_entry(task, cast(TaskQueueEntry, entry), self.alias)

    def _entry_to_result(self, task: Task, entry: TaskQueueEntry) -> TaskResult:
        return task_result_from_entry(task, entry, self.alias)

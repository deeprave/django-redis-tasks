import uuid
from asyncio import CancelledError
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Any

import django_queue
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.tasks.base import Task, TaskResultStatus
from django.tasks.exceptions import InvalidTask, TaskResultDoesNotExist
from django_queue import QueueRegistry

from redis_tasks.backend import RedisBackend, task_result_from_entry
from tests.tasks_fixtures import add, async_add, decorated_add


def make_task(
    *,
    func: Callable[..., Any] = add,
    priority: int = 0,
    backend: str = "default",
    queue_name: str = "default",
    run_after: datetime | None = None,
    takes_context: bool = False,
) -> Task:
    return Task(
        func=func,
        priority=priority,
        backend=backend,
        queue_name=queue_name,
        run_after=run_after,
        takes_context=takes_context,
    )


class TestEnqueue:
    def test_requires_configured_queue_alias(self):
        with pytest.raises(
            ImproperlyConfigured,
            match="queue_alias 'missing' is not configured in QUEUES",
        ):
            RedisBackend(
                alias="default",
                params={"OPTIONS": {"queue_alias": "missing"}},
            )

    def test_requires_redis_async_queue_backend(self, monkeypatch):
        monkeypatch.setattr(
            django_queue,
            "queues",
            QueueRegistry(
                {
                    "default": {
                        "BACKEND": "django_queue.backends.memory.MemoryAsyncQueue",
                    }
                }
            ),
        )

        with pytest.raises(
            ImproperlyConfigured,
            match="must use a RedisAsyncQueue-compatible backend",
        ):
            RedisBackend(alias="default", params={})

    def test_chains_non_class_queue_backend_configuration_error(self, monkeypatch):
        monkeypatch.setattr(
            django_queue,
            "queues",
            QueueRegistry({"default": {"BACKEND": "builtins.len"}}),
        )

        with pytest.raises(
            ImproperlyConfigured,
            match="must use a RedisAsyncQueue-compatible backend",
        ) as exc_info:
            RedisBackend(alias="default", params={})

        assert isinstance(exc_info.value.__cause__, TypeError)

    def test_requires_task_queue_entry_class(self, monkeypatch):
        monkeypatch.setattr(
            django_queue,
            "queues",
            QueueRegistry(
                {
                    "default": {
                        "BACKEND": "django_queue.backends.redis.RedisAsyncPriorityQueueJson",
                    }
                }
            ),
        )

        with pytest.raises(
            ImproperlyConfigured,
            match="must configure an ENTRY_CLASS compatible with TaskQueueEntry",
        ):
            RedisBackend(alias="default", params={})

    def test_requires_redis_task_worker_class(self, monkeypatch):
        monkeypatch.setattr(
            django_queue,
            "queues",
            QueueRegistry(
                {
                    "default": {
                        "BACKEND": "django_queue.backends.redis.RedisAsyncPriorityQueueJson",
                        "ENTRY_CLASS": "redis_tasks.entries.TaskQueueEntry",
                    }
                }
            ),
        )

        with pytest.raises(
            ImproperlyConfigured,
            match="must configure a WORKER compatible with RedisTaskWorker",
        ):
            RedisBackend(alias="default", params={})

    def test_enqueue_returns_ready_result(self, redis_backend):
        task = make_task()
        result = redis_backend.enqueue(task, (1, 2), {})
        assert result.status == TaskResultStatus.READY
        uuid.UUID(result.id)

    def test_enqueue_accepts_async_task(self, redis_backend):
        task = make_task(func=async_add)
        result = redis_backend.enqueue(task, (1, 2), {})
        assert result.status == TaskResultStatus.READY

    def test_enqueue_preserves_priority(self, redis_backend, task_queue):
        task = make_task(priority=10)
        result = redis_backend.enqueue(task, (1, 2), {})

        assert task_queue.find(uuid.UUID(result.id)).priority == 10

    def test_enqueue_preserves_queue_name(self, redis_backend):
        task = make_task(queue_name="alternate")
        enqueued = redis_backend.enqueue(task, (1, 2), {})

        result = redis_backend.get_result(enqueued.id)
        assert result.task.queue_name == "alternate"

    def test_get_result_preserves_decorated_task_enqueue_settings(self, redis_backend):
        task = decorated_add.using(priority=50, queue_name="alternate")
        enqueued = redis_backend.enqueue(task, (1, 2), {})

        result = redis_backend.get_result(enqueued.id)
        assert result.task.priority == 50
        assert result.task.queue_name == "alternate"

    def test_enqueue_rejects_deferred_task(self, redis_backend):
        from datetime import UTC, datetime, timedelta

        with pytest.raises(InvalidTask):
            make_task(run_after=datetime.now(UTC) + timedelta(minutes=5))

    @pytest.mark.asyncio
    async def test_aenqueue_uses_native_queue_methods(
        self, redis_backend, task_queue, monkeypatch
    ):
        def synchronous_queue_method(*args, **kwargs):
            raise AssertionError("the synchronous queue API must not be used")

        monkeypatch.setattr(task_queue, "enqueue", synchronous_queue_method)
        monkeypatch.setattr(task_queue, "find", synchronous_queue_method)

        result = await redis_backend.aenqueue(make_task(), (1, 2), {})

        assert result.status == TaskResultStatus.READY
        assert (await task_queue.afind(uuid.UUID(result.id))).payload["args"] == [1, 2]


class TestGetResult:
    def test_get_result_succeeded(self, redis_backend, task_queue):
        entry_id = task_queue.enqueue(
            {
                "func": "tests.tasks_fixtures.add",
                "args": [1, 2],
                "kwargs": {},
                "takes_context": False,
            }
        )
        task_queue._mark_running(entry_id)
        task_queue._mark_succeeded(entry_id, 3)

        result = redis_backend.get_result(str(entry_id))
        assert result.status == TaskResultStatus.SUCCESSFUL
        assert result.return_value == 3

    def test_get_result_reconstructs_decorated_task(self, redis_backend, task_queue):
        entry_id = task_queue.enqueue(
            {
                "func": "tests.tasks_fixtures.decorated_add",
                "args": [1, 2],
                "kwargs": {},
                "takes_context": False,
            }
        )
        task_queue._mark_running(entry_id)
        task_queue._mark_succeeded(entry_id, 3)

        result = redis_backend.get_result(str(entry_id))
        assert result.task.func is decorated_add.func
        assert result.return_value == 3

    def test_get_result_preserves_worker_ids(self, redis_backend, task_queue):
        entry_id = task_queue.enqueue(
            {
                "func": "tests.tasks_fixtures.add",
                "args": [1, 2],
                "kwargs": {},
                "takes_context": False,
            }
        )
        entry = replace(task_queue.find(entry_id), worker_ids=["worker-1"])

        result = task_result_from_entry(make_task(), entry, "default")
        assert result.worker_ids == ["worker-1"]

    def test_get_result_failed(self, redis_backend, task_queue):
        entry_id = task_queue.enqueue(
            {
                "func": "tests.tasks_fixtures.always_fails",
                "args": [],
                "kwargs": {},
                "takes_context": False,
            }
        )
        task_queue._mark_running(entry_id)
        task_queue._mark_failed(entry_id, ValueError("deliberate failure"))

        result = redis_backend.get_result(str(entry_id))
        assert result.status == TaskResultStatus.FAILED
        assert len(result.errors) == 1
        assert result.errors[0].exception_class is ValueError

    def test_get_result_failed_with_non_builtin_exception_falls_back(
        self, redis_backend, task_queue
    ):
        class CustomError(Exception):
            pass

        entry_id = task_queue.enqueue(
            {
                "func": "tests.tasks_fixtures.always_fails",
                "args": [],
                "kwargs": {},
                "takes_context": False,
            }
        )
        task_queue._mark_running(entry_id)
        task_queue._mark_failed(entry_id, CustomError("custom failure"))

        result = redis_backend.get_result(str(entry_id))
        assert result.errors[0].exception_class is Exception

    def test_get_result_timeout_maps_to_failed(self, redis_backend, task_queue):
        entry_id = task_queue.enqueue(
            {
                "func": "tests.tasks_fixtures.always_fails",
                "args": [],
                "kwargs": {},
                "takes_context": False,
            }
        )
        task_queue._mark_running(entry_id)
        task_queue._mark_timed_out(entry_id)

        result = redis_backend.get_result(str(entry_id))
        assert result.status == TaskResultStatus.FAILED
        assert result.errors[0].exception_class is TimeoutError

    def test_get_result_cancelled_has_error(self, redis_backend, task_queue):
        entry_id = task_queue.enqueue(
            {
                "func": "tests.tasks_fixtures.always_fails",
                "args": [],
                "kwargs": {},
                "takes_context": False,
            }
        )
        task_queue._mark_running(entry_id)
        task_queue._mark_cancelled(entry_id)

        result = redis_backend.get_result(str(entry_id))
        assert result.status == TaskResultStatus.FAILED
        assert result.errors[0].exception_class is CancelledError

    def test_get_result_returns_stored_outcome_for_missing_function(
        self, redis_backend, task_queue
    ):
        entry_id = task_queue.enqueue(
            {
                "func": "tests.tasks_fixtures.does_not_exist",
                "args": [],
                "kwargs": {},
                "takes_context": False,
            }
        )
        task_queue._mark_running(entry_id)
        task_queue._mark_failed(entry_id, ImportError("missing task"))

        result = redis_backend.get_result(str(entry_id))
        assert result.status == TaskResultStatus.FAILED
        assert result.errors[0].exception_class is ImportError

    def test_get_result_returns_missing_context_task_failure(
        self, redis_backend, task_queue
    ):
        entry_id = task_queue.enqueue(
            {
                "func": "tests.tasks_fixtures.does_not_exist",
                "args": [],
                "kwargs": {},
                "takes_context": True,
            }
        )
        task_queue._mark_running(entry_id)
        task_queue._mark_failed(entry_id, ImportError("missing task"))

        result = redis_backend.get_result(str(entry_id))

        assert result.status == TaskResultStatus.FAILED
        assert result.errors[0].exception_class is ImportError

    def test_get_result_missing_raises(self, redis_backend):
        with pytest.raises(TaskResultDoesNotExist):
            redis_backend.get_result(str(uuid.uuid7()))

    def test_get_result_invalid_id_raises(self, redis_backend):
        with pytest.raises(TaskResultDoesNotExist):
            redis_backend.get_result("not-a-uuid")

    @pytest.mark.asyncio
    async def test_aget_result_uses_native_queue_methods(
        self, redis_backend, task_queue, monkeypatch
    ):
        entry_id = await task_queue.aenqueue(
            {
                "func": "tests.tasks_fixtures.add",
                "args": [1, 2],
                "kwargs": {},
                "takes_context": False,
            }
        )

        def synchronous_queue_method(*args, **kwargs):
            raise AssertionError("the synchronous queue API must not be used")

        monkeypatch.setattr(task_queue, "find", synchronous_queue_method)

        result = await redis_backend.aget_result(str(entry_id))

        assert result.status == TaskResultStatus.READY
        assert result.id == str(entry_id)

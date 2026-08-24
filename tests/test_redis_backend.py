import asyncio
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import django_queue
import pytest
import redis
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.tasks.base import Task, TaskResultStatus
from django.tasks.exceptions import InvalidTask, TaskResultDoesNotExist
from django.utils import timezone
from django_queue import QueueRegistry
from django_queue.backends.exceptions import QueueEmptyException
from django_queue.clock import ClockTime
from django_queue.entries import QueueEntryStatus

from redis_tasks.backend import (
    RedisBackend,
    _task_from_stored_fields,
    task_result_from_entry,
)
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

    def test_clear_removes_enqueued_entries(self, redis_backend):
        result = redis_backend.enqueue(make_task(), (1, 2), {})
        redis_backend.clear()
        with pytest.raises(TaskResultDoesNotExist):
            redis_backend.get_result(result.id)

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

    def test_backend_supports_defer(self, redis_backend):
        assert redis_backend.supports_defer is True

    def test_enqueue_omits_available_at_when_run_after_is_unset(
        self, redis_backend, task_queue, monkeypatch
    ):
        captured: dict[str, Any] = {}
        original = task_queue.enqueue

        def wrapped(payload, **kwargs):
            captured.update(kwargs)
            return original(payload, **kwargs)

        monkeypatch.setattr(task_queue, "enqueue", wrapped)
        redis_backend.enqueue(make_task(), (1, 2), {})

        assert "available_at" not in captured
        assert captured["priority"] == 0

    def test_enqueue_passes_utc_available_at_for_aware_run_after(
        self, redis_backend, task_queue, monkeypatch
    ):
        captured: dict[str, Any] = {}
        original = task_queue.enqueue
        run_after = datetime.now(ZoneInfo("America/New_York")) + timedelta(hours=2)

        def wrapped(payload, **kwargs):
            captured.update(kwargs)
            return original(payload, **kwargs)

        monkeypatch.setattr(task_queue, "enqueue", wrapped)
        redis_backend.enqueue(make_task(run_after=run_after), (1, 2), {})

        assert captured["available_at"] == ClockTime.from_datetime(
            run_after.astimezone(UTC)
        )

    def test_enqueue_accepts_deferred_task(self, redis_backend):
        run_after = datetime.now(UTC) + timedelta(minutes=5)
        result = redis_backend.enqueue(make_task(run_after=run_after), (1, 2), {})

        assert result.status == TaskResultStatus.READY
        uuid.UUID(result.id)

    def test_enqueue_rejects_pre_epoch_run_after(self, redis_backend):
        with pytest.raises(InvalidTask, match="Unix epoch"):
            redis_backend.enqueue(
                make_task(run_after=datetime(1969, 12, 31, tzinfo=UTC)),
                (1, 2),
                {},
            )

    def test_get_result_preserves_run_after(self, redis_backend):
        run_after = datetime.now(ZoneInfo("America/New_York")) + timedelta(hours=1)
        enqueued = redis_backend.enqueue(make_task(run_after=run_after), (1, 2), {})

        result = redis_backend.get_result(enqueued.id)
        assert result.task.run_after == run_after.astimezone(UTC)

    def test_payload_stores_run_after_as_utc_isoformat(self, redis_backend, task_queue):
        run_after = datetime.now(ZoneInfo("America/New_York")) + timedelta(minutes=15)
        result = redis_backend.enqueue(make_task(run_after=run_after), (1, 2), {})

        payload = task_queue.find(uuid.UUID(result.id)).payload
        stored = datetime.fromisoformat(payload["run_after"])
        assert timezone.is_aware(stored)
        assert stored == run_after.astimezone(UTC)
        assert payload["run_after"] == run_after.astimezone(UTC).isoformat()

    def test_naive_run_after_is_invalid_when_use_tz_enabled(self, redis_backend):
        with pytest.raises(InvalidTask, match="run_after must be an aware datetime"):
            make_task(
                run_after=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
            )

    def test_naive_run_after_uses_current_timezone_when_use_tz_disabled(
        self, redis_backend, task_queue, monkeypatch
    ):
        monkeypatch.setattr(settings, "USE_TZ", False)
        naive = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
        expected = ClockTime.from_datetime(
            timezone.make_aware(naive, timezone.get_current_timezone()).astimezone(UTC)
        )
        captured: dict[str, Any] = {}
        original = task_queue.enqueue

        def wrapped(payload, **kwargs):
            captured.update(kwargs)
            return original(payload, **kwargs)

        monkeypatch.setattr(task_queue, "enqueue", wrapped)
        result = redis_backend.enqueue(make_task(run_after=naive), (1, 2), {})

        assert result.status == TaskResultStatus.READY
        assert captured["available_at"] == expected
        assert (
            redis_backend.get_result(result.id).task.run_after == expected.to_datetime()
        )

    def test_get_result_reads_naive_run_after_when_use_tz_is_later_enabled(
        self, redis_backend, task_queue, monkeypatch
    ):
        monkeypatch.setattr(settings, "USE_TZ", False)
        naive = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
        expected = timezone.make_aware(
            naive, timezone.get_current_timezone()
        ).astimezone(UTC)
        result = redis_backend.enqueue(make_task(run_after=naive), (1, 2), {})

        monkeypatch.setattr(settings, "USE_TZ", True)
        restored = redis_backend.get_result(result.id)

        assert restored.task.run_after == expected
        assert timezone.is_aware(restored.task.run_after)

    def test_task_from_stored_fields_normalizes_naive_run_after_when_use_tz(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "USE_TZ", True)
        naive = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
        task = _task_from_stored_fields(
            func=add,
            priority=0,
            backend="default",
            queue_name="default",
            takes_context=False,
            run_after=naive,
        )
        assert task.run_after == timezone.make_aware(naive).astimezone(UTC)

    @pytest.mark.asyncio
    async def test_past_run_after_is_immediately_claimable(
        self, redis_backend, task_queue
    ):
        run_after = datetime.now(UTC) - timedelta(minutes=5)
        result = await redis_backend.aenqueue(
            make_task(run_after=run_after), (1, 2), {}
        )

        claimed = await task_queue.aclaim(uuid.uuid4(), 1)

        assert str(claimed.id) == result.id
        assert result.status == TaskResultStatus.READY

    @pytest.mark.asyncio
    async def test_aenqueue_passes_available_at(
        self, redis_backend, task_queue, monkeypatch
    ):
        captured: dict[str, Any] = {}
        original = task_queue.aenqueue
        run_after = datetime.now(UTC) + timedelta(minutes=3)

        async def wrapped(payload, **kwargs):
            captured.update(kwargs)
            return await original(payload, **kwargs)

        monkeypatch.setattr(task_queue, "aenqueue", wrapped)
        result = await redis_backend.aenqueue(
            make_task(run_after=run_after), (1, 2), {}
        )

        assert result.status == TaskResultStatus.READY
        assert captured["available_at"] == ClockTime.from_datetime(run_after)

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

    @pytest.mark.asyncio
    async def test_get_result_from_async_test(self, redis_backend, task_queue):
        result = await redis_backend.aenqueue(make_task(), (1, 2), {})
        fetched = redis_backend.get_result(result.id)
        assert fetched.id == result.id
        assert fetched.status == TaskResultStatus.READY

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
        assert result.errors[0].exception_class is asyncio.CancelledError

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

    @pytest.mark.parametrize(
        "run_after",
        [1, "not-a-date"],
        ids=["non-string", "invalid-iso"],
    )
    def test_get_result_corrupt_run_after_raises_does_not_exist(
        self, redis_backend, task_queue, run_after
    ):
        entry_id = task_queue.enqueue(
            {
                "func": "tests.tasks_fixtures.add",
                "args": [1, 2],
                "kwargs": {},
                "takes_context": False,
                "run_after": run_after,
            }
        )

        with pytest.raises(TaskResultDoesNotExist):
            redis_backend.get_result(str(entry_id))

    def test_get_result_pre_epoch_run_after_raises_invalid_task(
        self, redis_backend, task_queue
    ):
        entry_id = task_queue.enqueue(
            {
                "func": "tests.tasks_fixtures.add",
                "args": [1, 2],
                "kwargs": {},
                "takes_context": False,
                "run_after": datetime(1969, 12, 31, 23, 59, 59, tzinfo=UTC).isoformat(),
            }
        )

        with pytest.raises(InvalidTask, match="Unix epoch"):
            redis_backend.get_result(str(entry_id))

    @pytest.mark.parametrize(
        "run_after",
        [1, "not-a-date"],
        ids=["non-string", "invalid-iso"],
    )
    @pytest.mark.asyncio
    async def test_aget_result_corrupt_run_after_raises_does_not_exist(
        self, redis_backend, task_queue, run_after
    ):
        entry_id = await task_queue.aenqueue(
            {
                "func": "tests.tasks_fixtures.add",
                "args": [1, 2],
                "kwargs": {},
                "takes_context": False,
                "run_after": run_after,
            }
        )

        with pytest.raises(TaskResultDoesNotExist):
            await redis_backend.aget_result(str(entry_id))

    @pytest.mark.asyncio
    async def test_aget_result_pre_epoch_run_after_raises_invalid_task(
        self, redis_backend, task_queue
    ):
        entry_id = await task_queue.aenqueue(
            {
                "func": "tests.tasks_fixtures.add",
                "args": [1, 2],
                "kwargs": {},
                "takes_context": False,
                "run_after": datetime(1969, 12, 31, 23, 59, 59, tzinfo=UTC).isoformat(),
            }
        )

        with pytest.raises(InvalidTask, match="Unix epoch"):
            await redis_backend.aget_result(str(entry_id))

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


def test_configured_queue_aliases_are_redis_safe():
    pattern = re.compile(r"^[A-Za-z0-9_-]+$")
    for alias in settings.QUEUES:
        assert pattern.fullmatch(alias)
    for name in settings.TASKS["default"]["QUEUES"]:
        assert pattern.fullmatch(name)


def test_testcontainer_redis_is_version_7_or_newer(redis_url):
    client = redis.Redis.from_url(redis_url)
    try:
        major = int(client.info("server")["redis_version"].split(".", 1)[0])
    finally:
        client.close()
    assert major >= 7


async def _wait_for_claim(task_queue, *, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return await task_queue.aclaim(uuid.uuid4(), 1)
        except QueueEmptyException:
            await asyncio.sleep(0.05)
    raise AssertionError("deferred task was not promoted before timeout")


async def _queue_now(task_queue) -> datetime:
    return (await task_queue.clock.anow()).to_datetime()


class TestDeferredDispatch:
    @pytest.mark.asyncio
    async def test_future_task_is_not_claimed_early(self, redis_backend, task_queue):
        run_after = datetime.now(UTC) + timedelta(minutes=10)
        result = await redis_backend.aenqueue(
            make_task(run_after=run_after), (1, 2), {}
        )
        stored = await redis_backend.aget_result(result.id)
        entry = await task_queue.afind(uuid.UUID(result.id))

        with pytest.raises(QueueEmptyException):
            await task_queue.aclaim(uuid.uuid4(), 1)

        assert stored.status == TaskResultStatus.READY
        assert stored.worker_ids == []
        assert entry.status == QueueEntryStatus.QUEUED
        assert entry.worker_ids == []

    @pytest.mark.asyncio
    async def test_future_task_survives_queue_reconnect(
        self, redis_backend, task_queue, redis_url
    ):
        run_after = datetime.now(UTC) + timedelta(minutes=10)
        result = await redis_backend.aenqueue(
            make_task(run_after=run_after), (1, 2), {}
        )
        other = django_queue.QueueRegistry(
            {
                "default": {
                    "BACKEND": "django_queue.backends.redis.RedisAsyncPriorityQueueJson",
                    "LOCATION": redis_url,
                    "ENTRY_CLASS": "redis_tasks.entries.TaskQueueEntry",
                    "WORKER": "redis_tasks.worker.RedisTaskWorker",
                }
            }
        )["default"]
        try:
            with pytest.raises(QueueEmptyException):
                await other.aclaim(uuid.uuid4(), 1)
            entry = await other.afind(uuid.UUID(result.id))
        finally:
            await other.aclose()

        stored = await redis_backend.aget_result(result.id)
        assert stored.status == TaskResultStatus.READY
        assert stored.worker_ids == []
        assert entry.status == QueueEntryStatus.QUEUED

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_future_task_is_promoted_after_due_time(
        self, redis_backend, task_queue
    ):
        run_after = ((await task_queue.clock.anow()) + 5).to_datetime()
        result = await redis_backend.aenqueue(
            make_task(run_after=run_after), (1, 2), {}
        )

        claimed = await _wait_for_claim(task_queue, timeout=10)
        assert str(claimed.id) == result.id
        assert claimed.status == QueueEntryStatus.QUEUED

    @pytest.mark.asyncio
    async def test_due_tasks_are_claimed_by_priority_then_fifo(
        self, redis_backend, task_queue
    ):
        due = (await _queue_now(task_queue)) - timedelta(minutes=1)
        first_equal = await redis_backend.aenqueue(
            make_task(priority=10, run_after=due), (1, 0), {}
        )
        high = await redis_backend.aenqueue(
            make_task(priority=50, run_after=due), (2, 0), {}
        )
        second_equal = await redis_backend.aenqueue(
            make_task(priority=10, run_after=due), (3, 0), {}
        )
        low = await redis_backend.aenqueue(
            make_task(priority=1, run_after=due), (4, 0), {}
        )

        claimed_ids = [
            str((await task_queue.aclaim(uuid.uuid4(), 1)).id) for _ in range(4)
        ]
        assert claimed_ids == [
            high.id,
            first_equal.id,
            second_equal.id,
            low.id,
        ]

    @pytest.mark.asyncio
    async def test_queue_with_only_future_work_is_empty(
        self, redis_backend, task_queue
    ):
        future = datetime.now(UTC) + timedelta(minutes=30)
        await redis_backend.aenqueue(
            make_task(priority=100, run_after=future), (1, 2), {}
        )
        await redis_backend.aenqueue(
            make_task(priority=0, run_after=future), (3, 4), {}
        )

        with pytest.raises(QueueEmptyException):
            await task_queue.aclaim(uuid.uuid4(), 1)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "eligible",
        [
            pytest.param("immediate", id="immediate"),
            pytest.param("past_due", id="past_due"),
        ],
    )
    async def test_eligible_work_is_claimed_while_future_work_waits(
        self, redis_backend, task_queue, eligible
    ):
        now = await _queue_now(task_queue)
        future = await redis_backend.aenqueue(
            make_task(priority=100, run_after=now + timedelta(minutes=10)),
            (1, 0),
            {},
        )
        if eligible == "immediate":
            ready = await redis_backend.aenqueue(make_task(priority=0), (2, 0), {})
        else:
            ready = await redis_backend.aenqueue(
                make_task(priority=0, run_after=now - timedelta(seconds=1)),
                (2, 0),
                {},
            )

        claimed = await task_queue.aclaim(uuid.uuid4(), 1)
        stored_future = await redis_backend.aget_result(future.id)

        assert str(claimed.id) == ready.id
        with pytest.raises(QueueEmptyException):
            await task_queue.aclaim(uuid.uuid4(), 1)
        assert stored_future.status == TaskResultStatus.READY
        assert stored_future.worker_ids == []

    @pytest.mark.asyncio
    async def test_immediate_and_due_tasks_are_claimed_by_priority_before_future(
        self, redis_backend, task_queue
    ):
        now = await _queue_now(task_queue)
        future = await redis_backend.aenqueue(
            make_task(priority=100, run_after=now + timedelta(minutes=10)),
            (1, 0),
            {},
        )
        due = await redis_backend.aenqueue(
            make_task(priority=10, run_after=now - timedelta(seconds=1)),
            (2, 0),
            {},
        )
        immediate = await redis_backend.aenqueue(make_task(priority=1), (3, 0), {})

        claimed_ids = [
            str((await task_queue.aclaim(uuid.uuid4(), 1)).id) for _ in range(2)
        ]
        stored_future = await redis_backend.aget_result(future.id)

        assert claimed_ids == [due.id, immediate.id]
        with pytest.raises(QueueEmptyException):
            await task_queue.aclaim(uuid.uuid4(), 1)
        assert stored_future.status == TaskResultStatus.READY

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_earlier_future_is_claimed_before_later_future(
        self, redis_backend, task_queue
    ):
        now = await _queue_now(task_queue)
        later = await redis_backend.aenqueue(
            make_task(priority=100, run_after=now + timedelta(minutes=10)),
            (1, 0),
            {},
        )
        sooner = await redis_backend.aenqueue(
            make_task(
                priority=0,
                run_after=((await task_queue.clock.anow()) + 5).to_datetime(),
            ),
            (2, 0),
            {},
        )

        claimed = await _wait_for_claim(task_queue, timeout=10)
        stored_later = await redis_backend.aget_result(later.id)

        assert str(claimed.id) == sooner.id
        with pytest.raises(QueueEmptyException):
            await task_queue.aclaim(uuid.uuid4(), 1)
        assert stored_later.status == TaskResultStatus.READY

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_scheduled_tasks_are_claimed_by_priority_then_fifo_after_promotion(
        self, redis_backend, task_queue
    ):
        run_after = ((await task_queue.clock.anow()) + 5).to_datetime()
        first_equal = await redis_backend.aenqueue(
            make_task(priority=10, run_after=run_after), (1, 0), {}
        )
        high = await redis_backend.aenqueue(
            make_task(priority=50, run_after=run_after), (2, 0), {}
        )
        second_equal = await redis_backend.aenqueue(
            make_task(priority=10, run_after=run_after), (3, 0), {}
        )
        low = await redis_backend.aenqueue(
            make_task(priority=1, run_after=run_after), (4, 0), {}
        )

        first = await _wait_for_claim(task_queue, timeout=10)
        claimed_ids = [str(first.id)]
        for _ in range(3):
            claimed_ids.append(str((await task_queue.aclaim(uuid.uuid4(), 1)).id))
        assert claimed_ids == [
            high.id,
            first_equal.id,
            second_equal.id,
            low.id,
        ]

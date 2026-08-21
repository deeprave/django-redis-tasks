from dataclasses import replace

import pytest
from django.tasks.base import TaskResultStatus
from django.tasks.signals import task_finished, task_started
from django_queue.clock import DEFAULT_CLOCK
from django_queue.entries import QueueEntryStatus

from redis_tasks.backend import RedisBackend
from redis_tasks.entries import TaskQueueEntry
from redis_tasks.handlers import handle_task_entry


def make_entry(**payload_overrides):
    payload = {
        "func": "tests.tasks_fixtures.add",
        "args": [1, 2],
        "kwargs": {},
        "takes_context": False,
    }
    payload.update(payload_overrides)
    return TaskQueueEntry.create(
        queue="default", payload=payload, queued_at=DEFAULT_CLOCK.now()
    )


class TestHandleTaskEntry:
    @pytest.mark.asyncio
    async def test_calls_sync_function(self):
        entry = make_entry()
        result = await handle_task_entry(entry)
        assert result == 3

    @pytest.mark.asyncio
    async def test_calls_async_function(self):
        entry = make_entry(func="tests.tasks_fixtures.async_add")
        result = await handle_task_entry(entry)
        assert result == 3

    @pytest.mark.asyncio
    async def test_normalizes_return_value_for_queue_storage(self):
        entry = make_entry(
            func="tests.tasks_fixtures.returns_bytes", args=[], kwargs={}
        )

        result = await handle_task_entry(entry)

        assert result == "queued result"

    @pytest.mark.asyncio
    async def test_calls_decorated_sync_task(self):
        entry = make_entry(func="tests.tasks_fixtures.decorated_add")
        result = await handle_task_entry(entry)
        assert result == 3

    @pytest.mark.asyncio
    async def test_calls_decorated_async_task(self):
        entry = make_entry(func="tests.tasks_fixtures.decorated_async_add")
        result = await handle_task_entry(entry)
        assert result == 3

    @pytest.mark.asyncio
    async def test_provides_task_context(self):
        entry = make_entry(
            func="tests.tasks_fixtures.add_with_context", takes_context=True
        )
        result = await handle_task_entry(entry)
        assert result == {"result_id": str(entry.id), "value": 3}

    @pytest.mark.asyncio
    async def test_context_uses_redis_dispatch_timestamp(self):
        entry = replace(
            make_entry(
                func="tests.tasks_fixtures.context_timestamps",
                args=[],
                kwargs={},
                takes_context=True,
            ),
            status=QueueEntryStatus.RUNNING,
            dispatched_at=DEFAULT_CLOCK.now(),
        )

        result = await handle_task_entry(entry)

        timestamp = entry.dispatched_at.to_datetime().isoformat()
        assert result == {"started_at": timestamp, "last_attempted_at": timestamp}

    @pytest.mark.asyncio
    async def test_emits_started_signal_from_redis_backend(self):
        events = []

        def record(sender, task_result, **kwargs):
            events.append(task_result.status)

        task_started.connect(record, sender=RedisBackend)
        try:
            await handle_task_entry(make_entry())
        finally:
            task_started.disconnect(record, sender=RedisBackend)

        assert events == [TaskResultStatus.RUNNING]

    @pytest.mark.asyncio
    async def test_emits_started_signal_to_async_receivers(self):
        events = []

        async def record(sender, task_result, **kwargs):
            events.append(task_result.status)

        task_started.connect(record, sender=RedisBackend)
        try:
            result = await handle_task_entry(make_entry())
        finally:
            task_started.disconnect(record, sender=RedisBackend)

        assert result == 3
        assert events == [TaskResultStatus.RUNNING]

    @pytest.mark.asyncio
    async def test_does_not_emit_finished_signal_before_worker_settlement(self):
        events = []

        def record(sender, task_result, **kwargs):
            events.append(task_result.status)

        task_finished.connect(record, sender=RedisBackend)
        try:
            await handle_task_entry(make_entry())
        finally:
            task_finished.disconnect(record, sender=RedisBackend)

        assert events == []

    @pytest.mark.asyncio
    async def test_propagates_function_exception(self):
        entry = make_entry(func="tests.tasks_fixtures.always_fails", args=[], kwargs={})
        with pytest.raises(ValueError, match="deliberate failure"):
            await handle_task_entry(entry)

    @pytest.mark.asyncio
    async def test_records_task_raised_cancellation_as_failure(self):
        entry = make_entry(
            func="tests.tasks_fixtures.raises_cancelled_error", args=[], kwargs={}
        )

        with pytest.raises(RuntimeError, match="raised asyncio.CancelledError"):
            await handle_task_entry(entry)

    @pytest.mark.asyncio
    async def test_records_self_cancellation_as_failure(self):
        entry = make_entry(func="tests.tasks_fixtures.self_cancels", args=[], kwargs={})

        with pytest.raises(RuntimeError, match="raised asyncio.CancelledError"):
            await handle_task_entry(entry)

    @pytest.mark.asyncio
    async def test_propagates_unimportable_function(self):
        entry = make_entry(func="tests.tasks_fixtures.does_not_exist")
        with pytest.raises(ImportError):
            await handle_task_entry(entry)

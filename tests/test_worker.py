import asyncio
import logging
from uuid import UUID

import pytest
from django.tasks.base import TaskResultStatus
from django.tasks.signals import task_finished
from django_queue.entries import QueueEntry, QueueEntryStatus

from redis_tasks.backend import RedisBackend
from redis_tasks.entries import TaskQueueEntry
from redis_tasks.worker import RedisTaskWorker


@pytest.mark.asyncio
async def test_queue_uses_task_entry_type_with_empty_attempt_history(task_queue):
    entry_id = await task_queue.aenqueue(_task_payload())

    entry = await task_queue.afind(entry_id)

    assert isinstance(entry, TaskQueueEntry)
    assert entry.worker_ids == []


def test_task_entry_defaults_attempt_history_for_legacy_record():
    legacy_entry = QueueEntry.create(queue="default", payload=_task_payload())

    restored_entry = TaskQueueEntry.from_dict(legacy_entry.to_dict())

    assert isinstance(restored_entry, TaskQueueEntry)
    assert restored_entry.worker_ids == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reuse_worker", [False, True])
async def test_worker_records_every_dispatch_after_lease_recovery(
    task_queue, redis_backend, reuse_worker
):
    entry_id = await task_queue.aenqueue(_task_payload())
    worker = RedisTaskWorker({"default": task_queue}, {"default": None})
    first_claim = await task_queue.aclaim(worker._worker_id, 0.001)
    first_running = await worker._mark_running(task_queue, first_claim)

    assert first_running is not None
    assert first_running.worker_ids == [str(worker._worker_id)]
    assert (await task_queue.afind(entry_id)).worker_ids == [str(worker._worker_id)]

    await asyncio.sleep(0.01)
    recovered, discarded = await task_queue.arecover(1)

    assert (recovered, discarded) == (1, 0)
    assert (await task_queue.afind(entry_id)).worker_ids == [str(worker._worker_id)]

    second_worker = (
        worker
        if reuse_worker
        else RedisTaskWorker({"default": task_queue}, {"default": None})
    )
    second_claim = await task_queue.aclaim(second_worker._worker_id, 60)
    second_running = await second_worker._mark_running(task_queue, second_claim)

    assert second_running is not None
    expected_worker_ids = [str(worker._worker_id), str(second_worker._worker_id)]
    assert second_running.worker_ids == expected_worker_ids

    result = await redis_backend.aget_result(str(entry_id))
    assert result.worker_ids == expected_worker_ids
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_worker_warns_when_lost_claim_cannot_be_released(
    task_queue, monkeypatch, caplog
):
    entry_id = await task_queue.aenqueue(_task_payload())
    worker = RedisTaskWorker({"default": task_queue}, {"default": None})
    claimed_entry = await task_queue.aclaim(worker._worker_id, 60)

    async def cannot_mark_running(*args, **kwargs):
        return False

    async def cannot_release(*args, **kwargs):
        return False

    monkeypatch.setattr(task_queue._provider, "amark_running", cannot_mark_running)
    monkeypatch.setattr(task_queue, "arelease", cannot_release)

    with caplog.at_level(logging.WARNING, logger="redis_tasks.worker"):
        result = await worker._mark_running(task_queue, claimed_entry)

    assert result is None
    assert f"Lost claim for queue entry {entry_id} before release" in caplog.messages


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error", "expected_result_status", "expected_error_path"),
    [
        (QueueEntryStatus.SUCCEEDED, None, TaskResultStatus.SUCCESSFUL, None),
        (
            QueueEntryStatus.FAILED,
            {"type": "ValueError", "message": "deliberate failure"},
            TaskResultStatus.FAILED,
            "builtins.ValueError",
        ),
        (
            QueueEntryStatus.CANCELLED,
            None,
            TaskResultStatus.FAILED,
            "asyncio.exceptions.CancelledError",
        ),
        (
            QueueEntryStatus.TIMEOUT,
            None,
            TaskResultStatus.FAILED,
            "builtins.TimeoutError",
        ),
    ],
)
async def test_worker_emits_finished_after_terminal_outcome_settles(
    task_queue, status, error, expected_result_status, expected_error_path
):
    events = []

    async def record(sender, task_result, **kwargs):
        persisted_entry = await task_queue.afind(UUID(task_result.id))
        error_path = (
            task_result.errors[0].exception_class_path if task_result.errors else None
        )
        events.append((task_result.status, persisted_entry.status, error_path))

    task_finished.connect(record, sender=RedisBackend)
    try:
        entry_id = await task_queue.aenqueue(_task_payload())
        worker = RedisTaskWorker({"default": task_queue}, {"default": None})
        claimed_entry = await task_queue.aclaim(worker._worker_id, 60)
        running_entry = await worker._mark_running(task_queue, claimed_entry)

        assert running_entry is not None
        terminal_entry = await worker._settle_terminal(
            task_queue,
            running_entry,
            worker._worker_id,
            status,
            error=error,
        )
    finally:
        task_finished.disconnect(record, sender=RedisBackend)

    assert terminal_entry.status == status
    assert (await task_queue.afind(entry_id)).status == status
    assert events == [(expected_result_status, status, expected_error_path)]


def _task_payload():
    return {
        "func": "tests.tasks_fixtures.add",
        "args": [1, 2],
        "kwargs": {},
        "takes_context": False,
    }

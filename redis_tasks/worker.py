import logging
from dataclasses import replace
from typing import cast
from uuid import UUID

from django.tasks.signals import task_finished
from django_queue.backends.base import AsyncQueue
from django_queue.backends.redis.redisqueue import RedisAsyncQueue
from django_queue.backends.redis.worker import RedisAsyncQueueWorker
from django_queue.clock import MICROSECONDS_PER_SECOND
from django_queue.entries import QueueEntry, QueueEntryStatus

from redis_tasks.backend import task_from_payload, task_result_from_entry
from redis_tasks.entries import TaskQueueEntry

logger = logging.getLogger(__name__)


class RedisTaskWorker(RedisAsyncQueueWorker):
    """Persist task dispatch metadata and emit durable terminal signals."""

    async def _mark_running(
        self, queue: AsyncQueue, entry: QueueEntry
    ) -> TaskQueueEntry | None:
        redis_queue = cast(RedisAsyncQueue, queue)
        queued_entry = cast(TaskQueueEntry, await redis_queue.afind(entry.id))
        running_entry = replace(
            queued_entry,
            status=QueueEntryStatus.RUNNING,
            dispatched_at=await redis_queue.clock.anow(),
            worker_ids=[*queued_entry.worker_ids, str(self._worker_id)],
        )
        provider = self._providers[redis_queue]
        if await provider.amark_running(self._worker_id, running_entry):
            return running_entry
        if not await redis_queue.arelease(
            entry.id, self._worker_id, 1 / MICROSECONDS_PER_SECOND
        ):
            logger.warning("Lost claim for queue entry %s before release", entry.id)
        return None

    async def _settle_terminal(
        self,
        queue: AsyncQueue,
        entry: QueueEntry,
        worker_id: UUID,
        status: QueueEntryStatus,
        *,
        result: object | None = None,
        error: dict[str, str] | None = None,
    ) -> QueueEntry:
        """Emit ``task_finished`` only after the terminal entry is durable."""
        terminal_entry = await super()._settle_terminal(
            queue, entry, worker_id, status, result=result, error=error
        )
        if terminal_entry.status not in {
            QueueEntryStatus.SUCCEEDED,
            QueueEntryStatus.FAILED,
            QueueEntryStatus.CANCELLED,
            QueueEntryStatus.TIMEOUT,
        }:
            return terminal_entry

        task_entry = cast(TaskQueueEntry, terminal_entry)
        payload = task_entry.payload
        task = task_from_payload(
            payload, payload.get("backend", task_entry.queue), allow_missing=True
        )
        task_result = task_result_from_entry(task, task_entry, task.backend)
        await task_finished.asend(type(task.get_backend()), task_result=task_result)
        return terminal_entry

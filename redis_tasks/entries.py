from dataclasses import dataclass, field

from django_queue.entries import QueueEntry


@dataclass(frozen=True, slots=True)
class TaskQueueEntry(QueueEntry):
    """A queue entry with Django task dispatch-attempt metadata."""

    worker_ids: list[str] = field(default_factory=list)

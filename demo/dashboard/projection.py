"""Observer-backed, process-local rows for the Redis tasks dashboard."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_queue import QueueSubscription, queue_observer
from django_queue.entries import QueueEntry, QueueEntryStatus

from dashboard import catalogue

_DONE_STATES = frozenset(
    {
        QueueEntryStatus.SUCCEEDED.value,
        QueueEntryStatus.FAILED.value,
        QueueEntryStatus.CANCELLED.value,
        QueueEntryStatus.TIMEOUT.value,
    }
)


def _task_name(payload: Mapping[str, Any]) -> str:
    func = str(payload.get("func", ""))
    return func.rsplit(".", 1)[-1] if func else "unknown"


def _parse_run_after(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, UTC)
    return parsed


def board_column(state: str) -> str:
    if state in _DONE_STATES:
        return "done"
    return "scheduled"


def remaining_wait_seconds(run_after: datetime | None) -> float | None:
    if run_after is None:
        return None
    delta = (run_after - timezone.now()).total_seconds()
    return max(delta, 0.0)


class DashboardProjection:
    """Maintain JSON-ready entry rows from `demo` lifecycle snapshots."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._rows: dict[str, dict[str, Any]] = {}
        self._subscription: QueueSubscription | None = None
        self._version = 0

    def start(self) -> None:
        with self._lock:
            if self._subscription is not None:
                return
            self._subscription = queue_observer("demo", self.update)

    def refresh(self) -> None:
        with self._changed:
            if self._subscription is not None:
                self._subscription.unsubscribe()
                self._subscription = None
            self._rows.clear()
            self._version += 1
            self._changed.notify_all()
        self.start()

    def update(self, entry: QueueEntry) -> None:
        entry_id = str(entry.id)
        with self._changed:
            if entry.status is QueueEntryStatus.TERMINATED:
                self._rows.pop(entry_id, None)
                self._version += 1
                self._changed.notify_all()
                return

        payload = entry.payload if isinstance(entry.payload, Mapping) else {}
        kwargs = (
            payload.get("kwargs") if isinstance(payload.get("kwargs"), Mapping) else {}
        )
        run_after = _parse_run_after(payload.get("run_after"))
        state = entry.status.value
        row = {
            "id": entry_id,
            "state": state,
            "column": board_column(state),
            "task": _task_name(payload),
            "generation": kwargs.get("generation"),
            "attempt": kwargs.get("attempt"),
            "chain": kwargs.get("chain"),
            "run_after": run_after.isoformat() if run_after else None,
            "remaining_wait": remaining_wait_seconds(run_after)
            if board_column(state) == "scheduled"
            else None,
            "result": entry.result,
            "error": entry.error,
            "queued_at": entry.queued_at.to_timestamp(),
            "started_at": (
                entry.dispatched_at.to_timestamp() if entry.dispatched_at else None
            ),
            "finished_at": (
                entry.finished_at.to_timestamp() if entry.finished_at else None
            ),
        }
        with self._changed:
            self._rows[row["id"]] = row
            self._version += 1
            self._changed.notify_all()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            rows = [row.copy() for row in self._rows.values()]
        for row in rows:
            run_after = _parse_run_after(row.get("run_after"))
            row["column"] = board_column(row["state"])
            row["remaining_wait"] = (
                remaining_wait_seconds(run_after)
                if row["column"] == "scheduled"
                else None
            )
        rows.sort(key=lambda row: (row["queued_at"], row["id"]))
        return {
            "entries": rows,
            "samples": catalogue.recent_samples(),
            "pulse_stopped": catalogue.pulse_stopped(),
            "pulse_chain": catalogue.current_chain(),
        }

    def events(self) -> Iterator[str]:
        version = -1
        while True:
            with self._changed:
                if self._version == version:
                    self._changed.wait(timeout=1)
                version = self._version
            yield f"data: {json.dumps(self.snapshot())}\n\n"


projection = DashboardProjection()

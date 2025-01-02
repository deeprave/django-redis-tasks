from typing import Any, Dict
from django_tasks import Task, TaskResult, ResultStatus
from django_tasks.backends.base import BaseTaskBackend
from django_tasks.exceptions import ResultDoesNotExist

from .utils import deserialise_function, utc_datetime
from .taskqueue import RedisTaskQueue, TaskState


def result_status(value) -> ResultStatus | None:
    if not isinstance(value, TaskState):
        value = TaskState.value_of(value)
    match value:
        case TaskState.READY:
            return ResultStatus.NEW
        case TaskState.PROCESSING:
            return ResultStatus.RUNNING
        case TaskState.COMPLETED:
            return ResultStatus.SUCCEEDED
        case TaskState.FAILED, TaskState.TIMEOUT:
            return ResultStatus.FAILED
    return None


class RedisBackend(BaseTaskBackend):
    queue_class = RedisTaskQueue
    supports_defer = True  # Tasks can be enqueued with the run_after attribute
    supports_async_task = True  # Coroutines be enqueued
    supports_get_result = True  # Results can be retrieved after the fact (from **any** thread / process)

    def __init__(self, alias: str, params: Dict[str, Any]) -> None:
        """
        Any connections which need to be set up can be done here
        """

        self._queue_class = params.pop("queue_class", self.queue_class)
        self._location = params.pop("location", "redis://localhost:6379/0")
        self._params = {}
        for k in ("queue_name", "ttl", "encoding"):
            v = params.pop(k, None)
            if v is not None:
                self._params[k] = v
        self._task_queue = None  # lazy
        super().__init__(alias=alias, params=params)

    @property
    def queue(self) -> RedisTaskQueue:
        if not self._task_queue:
            self._task_queue = self.queue_class(self._location, self._params)
        return self._task_queue

    def _redis_to_taskresult(self, task: Task, qtask) -> TaskResult:
        result = TaskResult(
            task=task,
            id=qtask.task_key,
            status=result_status(qtask.state),
            enqueued_at=utc_datetime(qtask.enqueued_at),
            started_at=utc_datetime(qtask.started_at),
            finished_at=utc_datetime(qtask.finished_at),
            args=qtask.args,
            kwargs=qtask.kwargs,
            backend=self.alias,
        )
        if result.is_finished:
            for attribute in ("exception_class", "traceback", "return_value"):
                setattr(result, f"_{attribute}", getattr(qtask, attribute, None))
        return result

    def enqueue(self, task: Task, *args, **kwargs) -> TaskResult:
        """
        Queue up a task to be executed
        """
        self.validate_task(task)

        qtask = self.queue.add_task(task.func, *args, priority=task.priority, run_after=task.run_after, **kwargs)
        return self._redis_to_taskresult(task, qtask)

    def get_result(self, task_key: str) -> TaskResult:
        """
        Retrieve a result by its id (if one exists).
        If one doesn't, raises ResultDoesNotExist.
        """
        if qtask := self.queue.get_task_status(task_key):
            return self._redis_to_taskresult(
                Task(
                    priority=qtask.priority,
                    func=deserialise_function(qtask.fn),
                    backend=self.alias,
                    queue_name=self.queue.queue_name,
                    run_after=qtask.run_after,
                    enqueue_on_commit=False,
                ),
                qtask
            )
        raise ResultDoesNotExist(f"task_id = {task_key}")

    def close(self) -> None:
        """
        Close any connections opened as part of the constructor
        """
        self.queue.clear_tasks()

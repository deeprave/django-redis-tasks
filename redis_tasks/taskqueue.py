import asyncio
from enum import Enum
import json
import uuid
import logging
import inspect
from datetime import datetime
from types import SimpleNamespace
from typing import Dict, Callable, TypeAlias
from dataclasses import dataclass

import redis
from asgiref.sync import async_to_sync
from django_tasks.task import DEFAULT_PRIORITY
from django_tasks.utils import get_exception_traceback

from .utils import serialise_function, deserialise_function, utc_now
from .runqueue import register_queue
from .signals import task_enqueued, task_started, task_finished

Namespace: TypeAlias = SimpleNamespace

DEFAULT_TTL = 3600



defaultLogLevel = logging.DEBUG

def _log(message: str, *args, **kwargs):
    logger = logging.getLogger(__name__)
    level = kwargs.pop("level", defaultLogLevel)
    logger.log(level, message, *args, **kwargs)


DEFAULT_LOCATION = "redis://localhost:6379/0"


class TaskState(Enum):
    READY = "ready"
    WAITING = "waiting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"

    @property
    def done(self):
        return self in (TaskState.COMPLETED, TaskState.FAILED, TaskState.TIMEOUT)

    @classmethod
    def value_of(cls, value) -> "TaskState":
        return next((state for state in cls if value == state.value), None)


@dataclass
class RedisTaskQueue:
    """
    Tasks manager using redis sorted queues

    Uses a Redis client or url to determine the redis instance to use
    Prefixes all redis keys with a queue_name (default "task_queue")
    Applies a default TTL whenever a value is created or updated

    Use types.SimpleNamespace in memory for handling task attributes, and convert <->> dict <-> JSON
    """
    def __init__(self, location: str | redis.Redis = DEFAULT_LOCATION, options: Dict | None = None, **kwargs):
        self._redis = redis.from_url(location) if isinstance(location, str) else location
        options = (options or {}) | kwargs
        self._queue_name = options.get("queue_name", "task_queue")
        self._default_ttl = int(options.get("ttl", DEFAULT_TTL))
        self._encoding = options.get("encoding", "utf-8")
        try:
            asyncio.get_running_loop()
            async_to_sync(register_queue)(self.queue_name, self)
        except RuntimeError:
            register_queue(self.queue_name, self)

    @property
    def redis(self):
        return self._redis

    @property
    def default_ttl(self):
        return self._default_ttl

    @property
    def queue_name(self):
        return self._queue_name

    @property
    def encoding(self):
        return self._encoding

    def task_key(self, task_key: str):
        """Generate the key to store task detail"""
        return f"{self.queue_name}:task:{task_key}"

    def state_queue(self, state: TaskState):
        """Generate the state-specific priority queue name."""
        return f"{self.queue_name}:{state.value}"

    def encode_data(self, data: Namespace) -> bytes:
        return json.dumps(data.__dict__).encode(self.encoding)

    def decode_str(self, data: bytes | str) -> str:
        return data.decode(self.encoding) if isinstance(data, bytes) else data

    def decode_data(self, data: bytes | str) -> Namespace:
        if isinstance(data, bytes):
            data = data.decode(self.encoding)
        return Namespace(**json.loads(data))

    def add_task(
        self, func: Callable | str, *args, priority: int = 0, run_after: datetime | None = None, **kwargs
    ) -> Namespace:
        """Add a new task to the priority queue."""
        now = utc_now()
        if run_after:
            run_after = run_after.timestamp()
            if run_after <= now:
                run_after = None
        task_key = str(uuid.uuid4())
        task = Namespace(
            task_key=task_key,
            priority=priority,
            state=TaskState.READY.value,
            enqueued_at=now,
            started_at=None,
            finished_at=None,
            run_after=run_after,
            fn=serialise_function(func) if callable(func) else func,
            args=list(args),
            kwargs=kwargs,
        )
        task_store_key = self.task_key(task_key)

        # store the task details
        self.redis.setex(task_store_key, self.default_ttl, self.encode_data(task))
        # Then add the task_key to the "ready" or "waiting" queue with the provided priority
        queue = self.state_queue(TaskState.WAITING if run_after else TaskState.READY)

        self.redis.zadd(queue, {task_key.encode(self.encoding): priority})
        task_enqueued.send(self, queue=queue, task_key=task_key, task=task)

        _log(f"Task {task_key} added to {queue}, priority {priority}")
        return task

    async def dispatch(self) -> bool:
        task = await self.get_next_task()
        if not task:
            return False
        func = deserialise_function(task.fn)
        args, kwargs = task.args, task.kwargs
        result, exc = None, None
        try:
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
        except BaseException as e:
            if type(e) in (KeyboardInterrupt, asyncio.CancelledError):
                raise
            exc = e
            _log(f"{task.task_key}.{task.fn}: {exc}", loglevel=logging.WARNING, exc_info=True)
        await self.complete_task(task.task_key, result=result, exc=exc)
        return True

    _GET_NEXT_TASK_LUA = """
        local waiting_queue = KEYS[1]
        local ready_queue = KEYS[2]
        local processing_queue = KEYS[3]
        local task_store_key = KEYS[4]
    
        -- Get the current timestamp
        local current_time = tonumber(ARGV[2])
    
        -- Check the waiting queue for tasks that are ready to run
        local ready_tasks = redis.call('zrangebyscore', waiting_queue, '-inf', current_time, 'LIMIT', 0, 1)
        if #ready_tasks > 0 then
            local task_key = ready_tasks[1] -- Select the highest-priority task in the waiting queue
    
            -- Retrieve the task details
            local task_data = redis.call('get', task_store_key:format(task_key))
            -- And remove it
            redis.call('zrem', waiting_queue, task_key)
            if task_data then
                -- Add the task to the processing queue
                redis.call('zadd', processing_queue, ARGV[1], task_key)
                return {task_key, task_data}
            end
        end
    
        -- Check the ready queue for tasks
        local task_key = redis.call('zrevrange', ready_queue, 0, 0)[1]
        if task_key then
            local task_data = redis.call('get', task_store_key:format(task_key))
            redis.call('zrem', ready_queue, task_key)
            if task_data then
                -- Move the task from ready to the processing queue
                redis.call('zadd', processing_queue, ARGV[1], task_key)
                return {task_key, task_data}
            end
        end
        return nil
        """

    async def get_next_task(self) -> Namespace | None:
        """Get the next task and move to PROCESSING queue."""
        waiting_queue = self.state_queue(TaskState.WAITING)
        ready_queue = self.state_queue(TaskState.READY)
        processing_queue = self.state_queue(TaskState.PROCESSING)
        now = utc_now()
        # first, check the waiting queue for any task that can be started
        # if none found, check the ready queue in order by priority
        lua_result = self.redis.eval(
            self._GET_NEXT_TASK_LUA,
            4,
            waiting_queue,
            ready_queue,
            processing_queue,
            f"{self.queue_name}:task:%s",
            DEFAULT_PRIORITY,
            str(now),  # Provide the current timestamp to Lua for time checks
        )
        if not lua_result:
            return None
        task_key, task_data = lua_result
        task_key = self.decode_str(task_key)
        task = self.decode_data(task_data)
        from_queue = self.state_queue(TaskState.value_of(task.state))
        task.state = TaskState.PROCESSING.value
        task.started_at = now

        self.redis.setex(self.task_key(task_key), self.default_ttl, self.encode_data(task))  # noqa
        task_started.send(self, queue=from_queue, task_key=task_key, task=task)

        _log(f"Task {task_key} moved from {from_queue} to {processing_queue} with priority {task.priority}")
        return task

    def _mark_completed(
        self, task_key: str, state: TaskState, result=None, exc: Exception | None = None
    ) -> bool:
        task_store_key = self.task_key(task_key)
        if task_data := self.redis.get(task_store_key):
            task = self.decode_data(task_data)
            task.state = state.value
            task.finished_at = utc_now(),
            if exc:
                task.exception_class = exc.__class__.__name__
                task.traceback = get_exception_traceback(exc)
            if result:
                task.return_value = result

            self.redis.setex(task_store_key, self.default_ttl * 2, self.encode_data(task))
            task_finished.send(self, queue=self.state_queue(TaskState.PROCESSING), task_key=task_key, task=task)

            _log(f"Task {task_key} marked as {state.name}")
            return True
        return False

    async def complete_task(self, task_key: str, result=None, exc: Exception | None = None):
        """Mark a task as COMPLETED or FAILED."""
        state = TaskState.FAILED if exc else TaskState.COMPLETED
        return self._mark_completed(task_key, state, result=result, exc=exc)

    def get_task_status(self, task_key: str):
        return async_to_sync(self.get_task_status_async)(task_key)

    async def get_task_status_async(self, task_key: str) -> Namespace | None:
        """Retrieve the current state and details of a task."""
        task_store_key = self.task_key(task_key)
        if task_data := self.redis.get(task_store_key):
            return self.decode_data(task_data)
        _log(f"Task {task_key} not found", level=logging.WARNING)
        return None

    def clear_tasks(self):
        """Removes all task records and clear all status queues for the queue_name."""
        # Clear all task records (those matching task_store_key format)
        task_pattern = f"{self.queue_name}:task:*"
        for key_batch in self.redis.scan_iter(match=task_pattern, count=1000):
            self.redis.delete(key_batch)

        # Clear all state queues (those matching state_queue format)
        for state in TaskState:
            state_queue = self.state_queue(state)
            if self.redis.exists(state_queue):  # Check if the queue exists
                self.redis.delete(state_queue)

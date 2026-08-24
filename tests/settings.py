import os

SECRET_KEY = "django-redis-tasks-tests"
USE_TZ = True
INSTALLED_APPS: list[str] = []

TASKS = {
    "default": {
        "BACKEND": "redis_tasks.backend.RedisBackend",
        "QUEUES": ["default", "queue_1", "alternate"],
    },
    "immediate": {
        "BACKEND": "django.tasks.backends.immediate.ImmediateBackend",
        "QUEUES": [],
    },
    "missing": {"BACKEND": "does.not.exist"},
}

QUEUES = {
    "default": {
        "BACKEND": "django_queue.backends.redis.RedisAsyncPriorityQueueJson",
        "LOCATION": os.environ.get("REDIS_TASKS_TEST_URL", "redis://127.0.0.1:6379/0"),
        "ENTRY_CLASS": "redis_tasks.entries.TaskQueueEntry",
        "WORKER": "redis_tasks.worker.RedisTaskWorker",
    }
}

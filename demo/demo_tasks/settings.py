"""Settings for the database-free Redis tasks demo."""

import os

SECRET_KEY = os.environ.get("DEMO_SECRET_KEY", "demo-only-not-for-production")
DEBUG = os.environ.get("DEMO_DEBUG", "true").lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DEMO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "django_queue.apps.DjangoQueueConfig",
    "redis_tasks.apps.RedisTasksConfig",
    "dashboard.apps.DashboardConfig",
]

MIDDLEWARE: list[str] = []
ROOT_URLCONF = "demo_tasks.urls"
WSGI_APPLICATION = "demo_tasks.wsgi.application"
ASGI_APPLICATION = "demo_tasks.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

STATIC_URL = "static/"
USE_TZ = True

QUEUES = {
    "demo": {
        "BACKEND": "django_queue.backends.redis.RedisAsyncPriorityQueueJson",
        "LOCATION": os.environ.get("DEMO_REDIS_URL", "redis://127.0.0.1:16399/0"),
        "TIMEOUT": 300,
        "RETENTION_TIMEOUT": 120,
        "HANDLER": "redis_tasks.handlers.handle_task_entry",
        "ENTRY_CLASS": "redis_tasks.entries.TaskQueueEntry",
        "WORKER": "redis_tasks.worker.RedisTaskWorker",
    }
}

TASKS = {
    "default": {
        "BACKEND": "redis_tasks.backend.RedisBackend",
        "OPTIONS": {
            "queue_alias": "demo",
        },
    }
}

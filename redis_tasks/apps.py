from asgiref.sync import async_to_sync
from django.apps import AppConfig

from .runqueue import start_task_queues


class RedisTasksConfig(AppConfig):
    name = "redis_tasks"
    verbose_name = "Redis Tasks"

    def ready(self):
        # Start the asyncio task to process the queues
        async_to_sync(start_task_queues)()

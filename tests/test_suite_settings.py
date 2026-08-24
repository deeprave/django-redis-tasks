from django.conf import settings
from django.tasks import task_backends
from django.test import SimpleTestCase

from redis_tasks.backend import RedisBackend


class TestSuiteDjangoSettings(SimpleTestCase):
    def test_default_task_backend_setting_is_redis(self):
        self.assertEqual(
            settings.TASKS["default"]["BACKEND"],
            "redis_tasks.backend.RedisBackend",
        )


def test_default_task_backend_is_redis_instance(redis_url):
    assert isinstance(task_backends["default"], RedisBackend)

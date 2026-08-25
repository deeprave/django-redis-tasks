"""ASGI configuration for the Redis tasks demo."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo_tasks.settings")

application = get_asgi_application()

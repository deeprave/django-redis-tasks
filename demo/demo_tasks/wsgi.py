"""WSGI configuration for the Redis tasks demo."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo_tasks.settings")

application = get_wsgi_application()

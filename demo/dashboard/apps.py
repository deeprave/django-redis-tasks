from django.apps import AppConfig


class DashboardConfig(AppConfig):
    name = "dashboard"

    def ready(self) -> None:
        from dashboard import catalogue

        catalogue.ensure_var_dir()

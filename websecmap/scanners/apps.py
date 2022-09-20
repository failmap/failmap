from django.apps import AppConfig


class ScannersConfig(AppConfig):
    name = "websecmap.scanners"

    def ready(self):
        import websecmap.scanners.signals  # noqa

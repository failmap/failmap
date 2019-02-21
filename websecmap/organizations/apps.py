from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    name = 'websecmap.organizations'

    def ready(self):
        import websecmap.organizations.signals  # noqa

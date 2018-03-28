from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    name = 'failmap.organizations'

    def ready(self):
        import failmap.organizations.signals  # noqa

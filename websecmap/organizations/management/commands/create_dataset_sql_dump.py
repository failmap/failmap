import logging
from pprint import pprint

from django.apps import apps
from django.core.management import BaseCommand

from websecmap.map.models import AdministrativeRegion, Configuration, LandingPage
from websecmap.organizations.models import Coordinate, Dataset, Organization, OrganizationType, Url
from websecmap.scanners.models import (Endpoint, EndpointGenericScan, InternetNLV2Scan,
                                       InternetNLV2StateLog, PlannedScan, ScanProxy, UrlGenericScan)

full_apps = ["api", "game", "constance", "django_celery_beat"]

log = logging.getLogger(__package__)


class Command(BaseCommand):

    def handle(self, *app_labels, **options):
        tables = []

        for full_model in full_apps:
            app_models = apps.get_app_config(full_model).get_models()
            for model in app_models:
                tables.append(model.objects.model._meta.db_table)

        for model in [OrganizationType, Organization, Coordinate, Url, Dataset, Endpoint, EndpointGenericScan,
                      UrlGenericScan, InternetNLV2Scan, InternetNLV2StateLog, ScanProxy, PlannedScan, Configuration,
                      AdministrativeRegion, LandingPage]:
            tables.append(model.objects.model._meta.db_table)

        pprint(tables)

        # sudo cp /root/.my.cnf ~/
        print(f"mysqldump -u [todo] -p [todo] "
              f"--add-drop-database --add-drop-table --single-transaction {','.join(tables)}")

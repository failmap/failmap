import logging
from pprint import pprint

from django.core.management import BaseCommand


from django.apps import apps

from websecmap.organizations.models import (OrganizationType, Organization, Coordinate, Url, Dataset)
from websecmap.scanners.models import (Endpoint, EndpointGenericScan, UrlGenericScan, InternetNLV2Scan, 
                                       InternetNLV2StateLog, ScanProxy, PlannedScan)
from websecmap.map.models import (Configuration, AdministrativeRegion, LandingPage)

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

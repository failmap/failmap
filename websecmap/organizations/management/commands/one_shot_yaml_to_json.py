import json
import logging
from datetime import date, datetime

import yaml
from django.core.management.base import BaseCommand
from pytz import timezone

log = logging.getLogger(__package__)

AMSTERDAM = timezone('Europe/Amsterdam')


class Command(BaseCommand):
    """
    Convert YAML dumps to json. YAML has an issue with non localized datetimes. This causes tons of warnings which
    CAN be hard to suppress in testcases and whatnot. So no YAML for this project. If you need to convert, you can
    use this.
    """

    def handle(self, *args, **options):

        with open("websecmap/organizations/fixtures/testdata.yaml", 'r'
                  ) as yaml_in, open("websecmap/organizations/fixtures/testdata.json", "w") as json_out:

            yaml_object = yaml.safe_load(yaml_in)  # yaml_object will be a list or a dict

            json.dump(yaml_object, json_out, default=json_serial)


def json_serial(obj):
    # assumption that UTC is used or acceptable. Make this timezone aware.

    if isinstance(obj, datetime):
        return AMSTERDAM.localize(obj).isoformat()

    if isinstance(obj, date):
        dt = datetime.combine(obj, datetime.min.time())
        return AMSTERDAM.localize(dt).date().isoformat()

    return obj

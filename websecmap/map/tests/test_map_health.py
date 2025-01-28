from datetime import datetime

import pytz

from websecmap.map.logic.map_health import update_map_health_reports
from websecmap.map.map_configs import filter_map_configs
from websecmap.map.models import Configuration, MapHealthReport
from websecmap.organizations.models import Organization, OrganizationType


def test_filter_map_configs(db):
    municipality = OrganizationType.objects.create(name="municipality")
    government = OrganizationType.objects.create(name="government")

    # insert other configurations to make sure only the right one is retrieved
    config_1 = Configuration.objects.create(country="NL", organization_type=municipality, is_reported=False)
    Configuration.objects.create(country="NL", organization_type=government, is_reported=False)
    Configuration.objects.create(country="BE", organization_type=municipality, is_reported=False)
    Configuration.objects.create(country="BE", organization_type=government, is_reported=False)

    # not reported, so not included
    configs = filter_map_configs(
        countries=["NL"],
        organization_types=["municipality"],
    )
    assert len(configs) == 0

    config_1.is_reported = True
    config_1.save()

    # only country filtered
    configs = filter_map_configs(
        countries=["NL"],
    )
    assert len(configs) == 1

    # only organization_type filtered
    configs = filter_map_configs(
        organization_types=["municipality"],
    )
    assert len(configs) == 1

    # both are filltered
    configs = filter_map_configs(
        countries=["NL"],
        organization_types=["municipality"],
    )
    assert len(configs) == 1


def test_update_map_health_reports(db):
    municipality = OrganizationType.objects.create(name="municipality")
    Configuration.objects.create(country="NL", organization_type=municipality, is_reported=True)
    Organization.objects.create(country="NL", created_on=datetime(2020, 1, 1, tzinfo=pytz.UTC))

    # make sure it doesn't crash on the type field
    tasks = update_map_health_reports("test", 1, ["NL"], ["municipality"])
    for task in tasks:
        task.apply()

    assert MapHealthReport.objects.all().count() == 1

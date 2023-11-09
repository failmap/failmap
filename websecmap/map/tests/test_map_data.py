from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta

from websecmap.map.logic.map import get_altnames, get_cached_map_data, get_map_data
from websecmap.map.models import MapDataCache
from websecmap.organizations.models import AlternativeName, Organization, OrganizationType


def test_get_cached_map_data(db):
    expected_result = {"test": "hello world"}

    ot = OrganizationType()
    ot.name = "test"
    ot.save()

    mdc = MapDataCache()
    mdc.country = "NL"
    mdc.organization_type = ot
    mdc.at_when = datetime.now(timezone.utc) - relativedelta(days=8)
    mdc.dataset = expected_result
    mdc.filters = ["all"]
    mdc.save()

    assert get_map_data(country="NL", organization_type="test", days_back=8) == expected_result
    assert get_cached_map_data(country="NL", organization_type="test", days_back=8) == expected_result
    assert get_cached_map_data(country="NL", organization_type="test", at_date=mdc.at_when) == expected_result


def test_get_altnames(db):
    org = Organization.objects.create(name="test")
    assert get_altnames(org.id) == ""

    altname_1 = AlternativeName.objects.create(name="test1")
    altname_2 = AlternativeName.objects.create(name="test2")
    altname_3 = AlternativeName.objects.create(name="test3")
    altname_4 = AlternativeName.objects.create(name="test4")

    org.alternative_names.add(altname_1, altname_2, altname_3, altname_4)

    assert get_altnames(org.id) == "test1 test2 test3 test4"

    # organization does not exist:
    assert get_altnames(None) == ""
    assert get_altnames(1231234) == ""

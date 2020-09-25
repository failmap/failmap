from datetime import datetime

import pytz
from dateutil.relativedelta import relativedelta

from websecmap.map.logic.map import get_map_data, get_cached_map_data
from websecmap.map.models import MapDataCache
from websecmap.organizations.models import OrganizationType


def test_get_cached_map_data(db):

    expected_result = {"test": "hello world"}

    ot = OrganizationType()
    ot.name = "test"
    ot.save()

    mdc = MapDataCache()
    mdc.country = "NL"
    mdc.organization_type = ot
    mdc.at_when = datetime.now(pytz.utc) - relativedelta(days=int(8))
    mdc.dataset = expected_result
    mdc.filters = ["all"]
    mdc.save()

    assert get_map_data(country="NL", organization_type="test", days_back=8) == expected_result
    assert get_cached_map_data(country="NL", organization_type="test", days_back=8) == expected_result

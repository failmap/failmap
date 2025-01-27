from datetime import datetime, timezone
from django.conf import settings
from dateutil.relativedelta import relativedelta
import pytest
from websecmap.map.logic.map import get_altnames, get_cached_map_data, get_map_data
from websecmap.map.models import MapDataCache
from websecmap.map.report import sync_model_field_to_disk
from websecmap.map.util import transparent_json_to_zip_storage, zip_to_json
from websecmap.organizations.models import AlternativeName, Organization, OrganizationType
from freezegun import freeze_time


def test_get_cached_map_data(db):
    # add some data that would be compressed in multiple chunks with high compression ratio to verify that
    # compression actually works.
    expected_result = {
        "test": "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
        "hello world hello world hello world hello world hello world hello world hello world hello world "
    }

    ot = OrganizationType()
    ot.name = "test"
    ot.save()

    mdc = MapDataCache()
    mdc.country = "NL"
    mdc.organization_type = ot
    mdc.at_when = datetime.now(timezone.utc) - relativedelta(days=8)
    mdc.dataset = None
    mdc.dataset_file = transparent_json_to_zip_storage(expected_result)
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


def test_sync_model_field_to_disk(db):
    expected_result = {"test": "hello world hello world hello world hello world hello world hello"}

    ot = OrganizationType()
    ot.name = "test"
    ot.save()

    # the old situation, nothing is in dataset_file
    mdc = MapDataCache()
    mdc.country = "NL"
    mdc.organization_type = ot
    mdc.at_when = datetime.now(timezone.utc) - relativedelta(days=8)
    mdc.dataset = expected_result
    mdc.dataset_file = None
    mdc.filters = ["all"]
    mdc.save()

    sync_model_field_to_disk(model=MapDataCache, json_field="dataset", file_field="dataset_file")

    mdc = MapDataCache.objects.all().first()
    assert mdc.dataset is None
    assert zip_to_json(mdc.dataset_file) == expected_result

    # running it again does not overwrite the file field with empty data(!)
    sync_model_field_to_disk(model=MapDataCache, json_field="dataset", file_field="dataset_file")

    mdc = MapDataCache.objects.all().first()
    assert mdc.dataset is None
    assert zip_to_json(mdc.dataset_file) == expected_result


def test_return_not_found_if_early(db, client):
    """if reports and map_data cache are not generated yet early in the morning we should return 404"""

    MapDataCache.objects.get_or_create(
        country="NL",
        organization_type=OrganizationType.objects.get_or_create(name="test")[0],
        at_when="2024-01-01",
    )[1]

    with freeze_time("2024-01-01 01:00:00"):
        response = client.get("/data/map/NL/test/2024-01-01/")
        assert response.status_code == 404
        assert "expires" not in response.headers, "404's should not be cached by django"


def test_return_not_found_if_future(db, client):
    """don't return mapdata for future dates"""

    MapDataCache.objects.get_or_create(
        country="NL",
        organization_type=OrganizationType.objects.get_or_create(name="test")[0],
        at_when="2024-01-01",
    )[1]

    with freeze_time("2024-01-01 01:00:00"):
        response = client.get("/data/map/NL/test/2024-01-02/")
        assert response.status_code == 404
        assert "expires" not in response.headers, "404's should not be cached by django"


@pytest.mark.skipif(settings.DB_ENGINE == "postgresql_psycopg2", reason="uses raw query not compatible with postgres")
def test_return_data_if_available(db, client):
    """available mapdata should be returned during the day"""

    MapDataCache.objects.get_or_create(
        country="NL",
        organization_type=OrganizationType.objects.get_or_create(name="test")[0],
        at_when="2024-01-01",
    )

    with freeze_time("2024-01-01 08:00:00"):
        response = client.get("/data/map/NL/test/2024-01-01/")
        assert response.status_code != 404
        assert "expires" in response.headers, "data should be cached"
        assert response.json()

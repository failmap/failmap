import json
from pathlib import Path
from unittest.mock import patch

import requests
from constance import config
from django.utils import timezone
from requests.models import Response

from websecmap.map.logic.openstreetmap import import_from_scratch
from websecmap.map.models import AdministrativeRegion, OrganizationType
from websecmap.organizations.models import Coordinate, Organization, Url

path = Path(__file__).parent


def file_get_contents(filepath):
    # does this read the entire file?
    with open(filepath, "rb") as content_file:
        return content_file.read()


def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, content, status_code):
            self.content = content
            self.status_code = status_code
            self.response = Response()

        def raise_for_status(self):
            # we'll not simulate errors now.
            return

        def iter_content(self, chunk_size):
            # return an iterator over the current content.
            # simulate the iterator :)
            yield self.content

    if args[0].startswith("https://osm-boundaries.com/"):
        return MockResponse(file_get_contents(f"{path}/openstreetmap/AL_county.gz"), 200)

    if args[0].startswith("http://www.overpass-api.de/api/interpreter"):
        return MockResponse(file_get_contents(f"{path}/openstreetmap/AL_county.osm"), 200)

    return ""


def mock_get_property_from_code(entity, property):
    from websecmap.map.logic.wikidata import ISO3316_2_COUNTRY_CODE, OFFICIAL_WEBSITE

    if property == ISO3316_2_COUNTRY_CODE:
        return "NL"
    if property == OFFICIAL_WEBSITE:
        return "https://www.amsterdam.nl"

    raise ValueError("Property code not supported in test.")


def mocked_osm_to_geojson(filename):
    # osmtogeojson is not available in the test environment
    return json.load(open(f"{path}/openstreetmap/AL_county.polygons"))


def prepare_database():

    # An import created organizations, coordinates and urls.
    Coordinate.objects.all().delete()
    Url.objects.all().delete()
    Organization.objects.all().delete()

    ot, created = OrganizationType.objects.all().get_or_create(name="county")

    ar, created = AdministrativeRegion.objects.all().get_or_create(
        country="AL", organization_type=ot, admin_level=4, resampling_resolution=0.01
    )


# todo: for tests we need osmtogeojson, how to enforce?
def test_openstreetmaps(db, monkeypatch):
    """
    Simulate the download from wambachers and the generic OSM data download.

    :param db:
    :return:
    """
    monkeypatch.setattr(requests, "get", mocked_requests_get)
    monkeypatch.setattr(requests, "post", mocked_requests_get)

    # cannot get monkeypatching to work with the wikidata module...
    # # websecmap.map.logic.wikidata.get_property_from_code = mock_get_property_from_code

    with patch("websecmap.map.logic.openstreetmap.get_property_from_code", mock_get_property_from_code):
        with patch("websecmap.map.logic.openstreetmap.osm_to_geojson", mocked_osm_to_geojson):

            # test OSM import
            config.WAMBACHERS_OSM_CLIKEY = ""
            prepare_database()
            import_from_scratch(["AL"], ["county"], timezone.now())

            assert Organization.objects.all().count() == 3
            assert Url.objects.all().count() == 2
            assert Coordinate.objects.all().count() == 3

            # test wambachers import
            config.WAMBACHERS_OSM_CLIKEY = "enabled"
            prepare_database()
            import_from_scratch(["AL"], ["county"], timezone.now())

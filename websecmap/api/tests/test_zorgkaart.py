import json
import logging

import websecmap
from websecmap.api.apis.zorgkaart import (
    get_zorgkaart_data,
    organization_and_url_import,
    translate_zorgkaart_to_flat_organization,
)
from websecmap.organizations.models import Coordinate, Organization, OrganizationSurrogateId, OrganizationType, Url

log = logging.getLogger("websecmap")


def default_coordinate(argument):
    return [0, 0]


def get_json_from_file(filename):
    with open(filename, "r") as content_file:
        return json.load(content_file)


def test_get_zorgkaart_data(db, requests_mock, current_path):
    url = "https://api.zorgkaartnederland.nl/api/v3.3/externalpartners/companies"
    bogus_data = get_json_from_file(f"{current_path}/websecmap/api/tests/zorgkaart_testdata/example_ggz.json")
    requests_mock.get(f"{url}?type=ggz&page=1&limit=100", json=bogus_data)
    requests_mock.get(f"{url}?type=ggz&page=2&limit=100", json=bogus_data)
    requests_mock.get(f"{url}?type=ggz&page=3&limit=100", json=bogus_data)

    # performs 3 requests for 299 entities (but 6 during the test)
    data = get_zorgkaart_data(url, {"type": "ggz"})
    assert len(data) == 6


def test_zorgkaart_translation(db, current_path):
    json_data = get_json_from_file(f"{current_path}/websecmap/api/tests/zorgkaart_testdata/example_ggz.json")

    flat = translate_zorgkaart_to_flat_organization(json_data["items"])
    assert flat == [
        {
            "address": "Example 5, 1337 NV Roermond, Nederland",
            "city": "Roermond",
            "coordinate_area": [5.01995, 51.3924181],
            "coordinate_type": "Point",
            "country": "NL",
            "key_value_data": {
                "brand_name1": "The Example B.V.",
                "brand_name2": None,
                "is_organisation": False,
                "nickname": "EXAMPLE B.V.",
                "nr_of_ratings": 82,
                "parent": "d3bfe09541e123812361273c965",
                "score": 8.9492,
            },
            "layer": "ggz",
            "name": "Example Organization",
            "surrogate_id": "zorgkaart_00041237812367871014877fd599",
            "surrogate_ids": [
                {"id": "id", "source": "zorgkaart", "value": "00041237812367871014877fd599"},
                {"id": "hdl_id", "source": "zorgkaart", "value": 513513},
                {"id": "registration_number", "source": "zorgkaart", "value": "1554131"},
                {"id": "location_number", "source": "zorgkaart", "value": "54651331"},
                {"id": "agb_codes", "source": "zorgkaart", "value": "5165135561351"},
            ],
            "urls": ["https://www.example.nl/"],
        },
        {
            "address": "AnotherOne 123, 1202 CD Sliedrecht, Nederland",
            "city": "Sliedrecht",
            "coordinate_area": [5.7773358, 52.8281444],
            "coordinate_type": "Point",
            "country": "NL",
            "key_value_data": {
                "brand_name1": "Another One Sliedrecht",
                "brand_name2": "",
                "is_organisation": False,
                "nickname": "ANOTHERONE SLIEDRECHT",
                "nr_of_ratings": 23,
                "parent": None,
                "score": 9.0826,
            },
            "layer": "ggz",
            "name": "Another Organization",
            "surrogate_id": "zorgkaart_001eeeeeee22feee859d66b8a",
            "surrogate_ids": [
                {"id": "id", "source": "zorgkaart", "value": "001eeeeeee22feee859d66b8a"},
                {"id": "hdl_id", "source": "zorgkaart", "value": 123123},
                {"id": "registration_number", "source": "zorgkaart", "value": ""},
                {"id": "location_number", "source": "zorgkaart", "value": "000039513319"},
                {"id": "agb_codes", "source": "zorgkaart", "value": "123634"},
            ],
            "urls": ["https://www.example2.nl"],
        },
    ]


def test_add_flat_organizations(db, monkeypatch):
    # don't connect to google during a test, but there is ALREADY a coordinate in the dataset(!)
    monkeypatch.setattr(websecmap.api.apis.zorgkaart, "retrieve_geocode", default_coordinate)

    organization_type = OrganizationType(**{"name": "Zorg"})
    organization_type.save()

    example_data = [
        {
            "name": "StadHolland (Zorgverzekeraar)",
            "layer": "Zorg",
            "country": "NL",
            "city": "Schiedam",
            "coordinate_type": "Point",
            "coordinate_area": [4.4035898, 51.922178],
            "address": "'s-Gravelandseweg 555, 3119 XT Schiedam, Nederland",
            "surrogate_id": "zorgkaart_001eeeeeee22feee859d66b8a",
            "urls": ["https://www.stadholland.nl"],
            "key_value_data": {
                "brand_name1": "Another One Sliedrecht",
                "brand_name2": "",
                "is_organisation": False,
                "nickname": "ANOTHERONE SLIEDRECHT",
                "nr_of_ratings": 23,
                "parent": None,
                "score": 9.0826,
            },
            "surrogate_ids": [
                {"id": "hdl_id", "source": "zorgkaart", "value": 123123},
                {"id": "registration_number", "source": "zorgkaart", "value": ""},
                {"id": "location_number", "source": "zorgkaart", "value": "000039513319"},
                {"id": "agb_codes", "source": "zorgkaart", "value": "123634"},
            ],
        },
        {
            "name": "VvAA (Zorgverzekeraar)",
            "layer": "Zorg",
            "country": "NL",
            "city": "Utrecht",
            "coordinate_type": "Point",
            "coordinate_area": [5.080751, 52.0700558],
            "address": "Orteliuslaan 750, 3528 BB Utrecht, Nederland",
            "surrogate_id": "zorgkaart_001e123121239d66b8a",
            "urls": ["https://www.vvaa.nl"],
            "surrogate_ids": [
                {"id": "hdl_id", "source": "zorgkaart", "value": 513513},
                {"id": "registration_number", "source": "zorgkaart", "value": "1554131"},
                {"id": "location_number", "source": "zorgkaart", "value": "54651331"},
                {"id": "agb_codes", "source": "zorgkaart", "value": "5165135561351"},
            ],
            "key_value_data": {
                "brand_name1": "The Example B.V.",
                "brand_name2": None,
                "is_organisation": False,
                "nickname": "EXAMPLE B.V.",
                "nr_of_ratings": 82,
                "parent": "d3bfe09541e123812361273c965",
                "score": 8.9492,
            },
        },
        {
            "name": "Nationale-Nederlanden (Zorgverzekeraar)",
            "layer": "Zorg",
            "country": "NL",
            "coordinate_type": "Point",
            "coordinate_area": [5.056375, 51.5852528],
            "address": "Postbus 4016, 5004 JA Tilburg, Nederland",
            "surrogate_id": "Nationale-Nederlanden_Zorgverzekeraar_1651f4e08df73eb1b24673244dab2aeb",
            "urls": ["http://www.deltalloyd.nl"],
            "surrogate_ids": [
                {"id": "hdl_id", "source": "zorgkaart", "value": 513513},
                {"id": "registration_number", "source": "zorgkaart", "value": "1554131"},
                {"id": "location_number", "source": "zorgkaart", "value": "54651331"},
                {"id": "agb_codes", "source": "zorgkaart", "value": "5165135561351"},
            ],
            "key_value_data": {
                "brand_name1": "The Example B.V.",
                "brand_name2": None,
                "is_organisation": False,
                "nickname": "EXAMPLE B.V.",
                "nr_of_ratings": 82,
                "parent": "d3bfe09541e123812361273c965",
                "score": 8.9492,
            },
        },
    ]

    # nothing should be in the db
    assert Organization.objects.all().count() == 0

    # things should be added
    organization_and_url_import(example_data)
    assert Organization.objects.all().count() == 3
    # www and non www
    assert Url.objects.all().count() == 6
    assert Coordinate.objects.all().count() == 3

    # add this dataset again, and nothing new should be added
    organization_and_url_import(example_data)
    assert Organization.objects.all().count() == 3
    assert Url.objects.all().count() == 6
    assert Coordinate.objects.all().count() == 3

    # surrogates are loaded
    assert OrganizationSurrogateId.objects.all().count() == 12

    # key value data is stored
    org = Organization.objects.all().first()
    assert org.arbitrary_kv_data["brand_name1"] != ""

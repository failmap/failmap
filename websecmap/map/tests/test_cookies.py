from datetime import datetime, timezone
from constance.test import override_config

from freezegun import freeze_time

from websecmap.map.logic.cookie_plaza import cookie_plaza_data
from websecmap.map.logic.cookies import get_cookie_database
from websecmap.map.models import Configuration
from websecmap.organizations.models import Url, Organization, OrganizationType
from websecmap.scanners.models import (
    ProductCookieIndicator,
    CookiePurpose,
    Product,
    ProductVendor,
    Endpoint,
    EndpointGenericScan,
)
from django.test import Client
from django.urls import reverse


def test_get_cookie_database(db):
    v = ProductVendor.objects.create(name="Google")
    p = Product.objects.create(
        name="Google Analytics",
        vendor=v,
    )

    p2 = Product.objects.create(
        name="OWA",
    )
    marketing_cookie = CookiePurpose.objects.create(name="marketing")
    session_cookie = CookiePurpose.objects.create(name="session")

    i1 = ProductCookieIndicator.objects.create(match_name="_gat?", product=p, most_significant_purpose=marketing_cookie)
    i2 = ProductCookieIndicator.objects.create(
        match_name="cookieTest", match_path="/owa/auth.*", product=p2, most_significant_purpose=session_cookie
    )

    # add a link
    i3 = ProductCookieIndicator.objects.create(
        match_name="marco_v",
        product=p2,
        match_path="/dutyfree/indicator.*",
        cookiedatabase_link="http://example.com",
    )

    data = get_cookie_database()

    assert data == {
        # id's in json are not integers
        str(i1.id): {
            "cookie_database_link": None,
            "most_significant_purpose": "marketing",
            "notes": None,
            "product_id": 1,
            "product_vendor_id": 1,
        },
        str(i2.id): {
            "cookie_database_link": None,
            "most_significant_purpose": "session",
            "notes": None,
            "product_id": 2,
            "product_vendor_id": None,
        },
        str(i3.id): {
            "cookie_database_link": "http://example.com",
            "most_significant_purpose": None,
            "notes": None,
            "product_id": 2,
            "product_vendor_id": None,
        },
    }


@override_config(SHOW_COOKIE_PLAZA=False)
def test_cookie_plaza_data(db):
    # no data, should not result in a crash
    all_layers, all_stats = cookie_plaza_data()
    assert all_layers == []
    assert all_stats == {}

    # a few metrics in a few layers, should work fine and give some duplicate results
    with freeze_time("2022-01-24"):
        now = datetime.now(timezone.utc)
        url = Url.objects.create(url="example.nl")
        organization = Organization.objects.create(name="test", country="NL")
        url.organization.add(organization)
        layer = OrganizationType.objects.create(name="layer1")
        organization.layers.add(layer)
        organization.save()
        # make it visible as well...
        Configuration.objects.create(is_displayed=True, country="NL", organization_type=layer)

        ep = Endpoint.objects.create(url=url, discovered_on=now, port=443, protocol="https", ip_version=4)
        epgs = EndpointGenericScan.objects.create(
            type="web_privacy_cookie_products_no_consent",
            meaning={},
            endpoint=ep,
            is_the_latest_scan=True,
            comply_or_explain_is_explained=False,
            rating="medium",
            rating_determined_on=now,
        )
        all_layers, all_stats = cookie_plaza_data()
        assert len(all_layers) == 1
        assert all_layers == [
            {
                "cookies": {},
                "country": "NL",
                "domain": "example.nl",
                "last_scan_moment": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc).isoformat(),
                "layer": "layer1",
                "organization_id": organization.id,
                "organization_name": "test",
                "rating_determined_on": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc).isoformat(),
                "scan_id": epgs.id,
                "subdomain": "",
                "url_url": "example.nl",
            },
        ]

        assert all_stats == {
            "layer1": {
                "organizations_with_tracking_cookies": [organization.id],
                "urls_with_tracking_cookies": ["example.nl"],
                "organization_details": {
                    # json keys myst be strings
                    str(organization.id): {
                        "id": organization.name,
                        "name": organization.name,
                        "urls_with_tracking_cookies": ["example.nl"],
                    }
                },
            }
        }

        specific_layers, specific_stats = cookie_plaza_data("NL", "layer1")
        assert all_layers == specific_layers
        assert all_stats == specific_stats

    # perform call to test server to see if there are no sets returned
    client = Client()
    response = client.get(reverse("cookie_plaza"))
    assert response.status_code == 200

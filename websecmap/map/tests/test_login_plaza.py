from datetime import datetime

from django.utils import timezone
from freezegun import freeze_time

from websecmap.map.logic.login_plaza import login_plaza_data, get_nuclei_product_mapping, get_products
from websecmap.organizations.models import OrganizationType, Organization, Url
from websecmap.scanners.models import (
    Endpoint,
    EndpointGenericScan,
    ProductVendor,
    ProductGoal,
    ScannerFinding,
    ProductRelationship,
    Product,
    ProductHierarchy,
)


def create_test_product_data():
    # now let's add some products like it's phpmyadmin, add some nested products and other vendors.
    # this would return a list of technologies that are used
    vendor = ProductVendor.objects.create(name="Yolo Company")
    goal = ProductGoal.objects.create(name="Yolo-ing")
    finding_1 = ScannerFinding.objects.create(name="nuclei_citrix_adc_gateway_panel")
    finding_2 = ScannerFinding.objects.create(name="nuclei_netscaler_aaa_login")
    relationship = ProductRelationship.objects.create(name="something something something darkside")

    # add some random product, for the citrix panel
    product = Product.objects.create(
        name="phpmyadmin",
        vendor=vendor,
        goal=goal,
        intended_use_case_description="something",
        is_open_source=True,
        common_execution_environment="Server",
        is_irrelevant=False,
    )
    product.tags.add("tag 1")
    product.tags.add("tag 2")

    product.scanner_finding_name_mapping.add(finding_1)

    # add another random product, for the netscaler
    product2 = Product.objects.create(
        name="php",
        vendor=vendor,
        goal=goal,
        intended_use_case_description="something",
        is_open_source=True,
        common_execution_environment="Server",
        is_irrelevant=False,
    )
    product2.tags.add("tag 3")
    product2.tags.add("tag 4")

    product2.scanner_finding_name_mapping.add(finding_2)

    # also test that the relationship is created. So the citrix will also get the thing for the netscaler
    ProductHierarchy.objects.create(product=product, related_product=product2, relationship=relationship)


def test_login_plaza_data(db):
    with freeze_time("2022-01-24"):
        # no data, no crashes
        data = login_plaza_data("NL", "municipality")
        assert data == []

        # Prepare the data for a typical response
        organization_type, created = OrganizationType.objects.all().get_or_create(name="municipality")
        now = timezone.now()
        organization = Organization.objects.all().create(
            name="test", type=organization_type, country="NL", created_on=now, is_dead=False
        )
        organization.layers.add(organization_type)
        url = Url.objects.all().create(url="test.nl", created_on=now, is_dead=False, not_resolvable=False)
        url.organization.add(organization)
        url.save()
        endpoint = Endpoint.objects.create(url=url, port=443, protocol="https")

        evidence = """[ { "name": "Citrix ADC Gateway Login Panel - Detect", "finding-name": "nuclei_citrix_adc_gateway_panel", "evidence": { "extracted-results": ["13.37"], "matched-at": "https://nsg1.vumc.nl:443/logon/LogonPoint/index.html" } }, { "name": "NetScaler AAA Login Panel - Detect", "finding-name": "nuclei_netscaler_aaa_login", "evidence": { "extracted-results": [], "matched-at": "https://nsg1.vumc.nl:443/logon/LogonPoint/tmindex.html" } } ]"""  # noqa

        EndpointGenericScan.objects.create(
            endpoint=endpoint,
            evidence=evidence,
            type="nuclei_exposed_panels",
            rating_determined_on=now,
            is_the_latest_scan=True,
            rating="info",
        )

        # retrieve a typical response based on the single metrics we have in the db.
        data = login_plaza_data("NL", "municipality")

        # because reset sequences causes issues
        data[0]["organization_id"] = 1
        data[0]["scan_id"] = 1
        data[1]["organization_id"] = 1
        data[1]["scan_id"] = 1

        # there is no tech in the database yet, so you don't see any technology
        assert data == [
            {
                "organization_id": 1,
                "scan_id": 1,
                "domain": "test.nl",
                "last_scan_moment": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "organization_name": "test",
                "portal_extracted": ["13.37"],
                "portal_name": "Citrix ADC Gateway Login Panel",
                "portal_url": "https://nsg1.vumc.nl:443/logon/LogonPoint/index.html",
                "rating_determined_on": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "subdomain": "",
                "url_url": "test.nl",
                "tech": [],
            },
            {
                "organization_id": 1,
                "scan_id": 1,
                "domain": "test.nl",
                "last_scan_moment": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "organization_name": "test",
                "portal_extracted": [],
                "portal_name": "NetScaler AAA Login Panel",
                "portal_url": "https://nsg1.vumc.nl:443/logon/LogonPoint/tmindex.html",
                "rating_determined_on": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "subdomain": "",
                "url_url": "test.nl",
                "tech": [],
            },
        ]

        create_test_product_data()
        data = login_plaza_data("NL", "municipality")

        # because reset sequences causes issues:
        data[0]["organization_id"] = 1
        data[0]["scan_id"] = 1
        data[1]["organization_id"] = 1
        data[1]["scan_id"] = 1
        data[0]["tech"][0]["product"] = 1
        data[0]["tech"][1]["product"] = 2
        data[1]["tech"][0]["product"] = 1
        data[1]["tech"][1]["product"] = 2

        # there is no tech in the database yet, so you don't see any technology
        assert data == [
            {
                "organization_id": 1,
                "scan_id": 1,
                "domain": "test.nl",
                "last_scan_moment": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "organization_name": "test",
                "portal_extracted": ["13.37"],
                "portal_name": "Citrix ADC Gateway Login Panel",
                "portal_url": "https://nsg1.vumc.nl:443/logon/LogonPoint/index.html",
                "rating_determined_on": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "subdomain": "",
                "url_url": "test.nl",
                "tech": [
                    {
                        "product": 1,
                        "version": "13.37",
                    },
                    {
                        "product": 2,
                        "version": "unknown",
                    },
                ],
            },
            {
                "organization_id": 1,
                "scan_id": 1,
                "domain": "test.nl",
                "last_scan_moment": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "organization_name": "test",
                "portal_extracted": [],
                "portal_name": "NetScaler AAA Login Panel",
                "portal_url": "https://nsg1.vumc.nl:443/logon/LogonPoint/tmindex.html",
                "rating_determined_on": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "subdomain": "",
                "url_url": "test.nl",
                # Same endpoint, so same technologies.
                "tech": [
                    {
                        "product": 1,
                        "version": "13.37",
                    },
                    {
                        "product": 2,
                        "version": "unknown",
                    },
                ],
            },
        ]


def test_get_products(db):
    create_test_product_data()
    products = get_products()

    keys = list(products.keys())
    first_id = keys[0]
    second_id = keys[1]

    products[first_id]["id"] = 1
    products[second_id]["id"] = 2
    products[first_id]["vendor"]["id"] = 1
    products[second_id]["vendor"]["id"] = 1

    assert products == {
        str(first_id): {
            "common_execution_context": "Server",
            "cve_details_link": "",
            "open_cve_link": "",
            "goal": "Yolo-ing",
            "id": 1,
            "intended_use_case_description": "something",
            "is_open_source": True,
            "name": "phpmyadmin",
            "name_slug": "",
            "tags": ["tag 1", "tag 2"],
            "vendor": {"id": 1, "name": "Yolo Company", "slug": "yolo-company"},
        },
        str(second_id): {
            "common_execution_context": "Server",
            "cve_details_link": "",
            "open_cve_link": "",
            "goal": "Yolo-ing",
            "id": 2,
            "intended_use_case_description": "something",
            "is_open_source": True,
            "name": "php",
            "name_slug": "",
            "tags": ["tag 3", "tag 4"],
            "vendor": {"id": 1, "name": "Yolo Company", "slug": "yolo-company"},
        },
    }


def test_get_nuclei_product_mapping(db):
    create_test_product_data()
    mapping = get_nuclei_product_mapping()

    mapping["nuclei_citrix_adc_gateway_panel"][0]["product"] = 1
    mapping["nuclei_citrix_adc_gateway_panel"][1]["product"] = 2
    mapping["nuclei_netscaler_aaa_login"][0]["product"] = 2

    assert mapping == {
        "nuclei_citrix_adc_gateway_panel": [
            {
                "product": 1,
                "version": "unknown",
            },
            {
                "product": 2,
                "version": "unknown",
            },
        ],
        "nuclei_netscaler_aaa_login": [
            {
                "product": 2,
                "version": "unknown",
            }
        ],
    }

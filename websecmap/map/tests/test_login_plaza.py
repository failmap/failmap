import copy
from datetime import datetime, timezone

import pytest
from freezegun import freeze_time

from websecmap.map.logic.login_plaza import (
    get_nested_products_in_an_inefficient_way,
    get_nuclei_product_mapping,
    get_products,
    login_plaza_data,
    prioritize_tech,
    set_value_to_tech_in_tree,
    smash_tree,
    smash_trees,
    save_get_tech_for_endpoints,
)
from websecmap.organizations.models import Organization, OrganizationType, Url
from websecmap.scanners.models import (
    Endpoint,
    EndpointGenericScan,
    Product,
    ProductGoal,
    ProductHierarchy,
    ProductRelationship,
    ProductVendor,
    ScannerFinding,
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


def test_login_plaza_data(db, reset_time_cache):
    with freeze_time("2022-01-24"):
        # no data, no crashes
        data = login_plaza_data("NL", "municipality")
        assert data == []

        # Prepare the data for a typical response
        organization_type, created = OrganizationType.objects.all().get_or_create(name="municipality")
        now = datetime.now(timezone.utc)
        organization = Organization.objects.all().create(name="test", country="NL", created_on=now, is_dead=False)
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

        # create new tech metric:
        assert EndpointGenericScan.objects.all().filter(endpoint=endpoint).count() == 1
        save_get_tech_for_endpoints()
        assert EndpointGenericScan.objects.all().filter(endpoint=endpoint).count() == 2
        assert EndpointGenericScan.objects.all().filter(endpoint=endpoint, type="technology").count() == 1

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
                "organization_city": "",
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
                "organization_city": "",
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
                "organization_city": "",
                "portal_extracted": ["13.37"],
                "portal_name": "Citrix ADC Gateway Login Panel",
                "portal_url": "https://nsg1.vumc.nl:443/logon/LogonPoint/index.html",
                "rating_determined_on": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "subdomain": "",
                "url_url": "test.nl",
                "tech": [
                    {"product": 1, "version": "13.37"},
                    {"product": 2, "version": "unknown"},
                ],
            },
            {
                "organization_id": 1,
                "scan_id": 1,
                "domain": "test.nl",
                "last_scan_moment": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "organization_name": "test",
                "organization_city": "",
                "portal_extracted": [],
                "portal_name": "NetScaler AAA Login Panel",
                "portal_url": "https://nsg1.vumc.nl:443/logon/LogonPoint/tmindex.html",
                "rating_determined_on": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "subdomain": "",
                "url_url": "test.nl",
                # Same endpoint, so same technologies, but the product for this portal first.
                "tech": [
                    {"product": 1, "version": "unknown"},
                    {"product": 2, "version": "13.37"},
                ],
            },
        ]


def test_get_products(db, reset_time_cache):
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
            "slug": "phpmyadmin",
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
            "slug": "php",
            "tags": ["tag 3", "tag 4"],
            "vendor": {"id": 1, "name": "Yolo Company", "slug": "yolo-company"},
        },
    }


def test_get_nuclei_product_mapping(db, reset_time_cache):
    create_test_product_data()

    first_product = Product.objects.all().first()
    nested = get_nested_products_in_an_inefficient_way(first_product)
    nested[0]["product"] = 2
    assert nested == [
        {
            "product": 2,
            "relationship": "something-something-something-darkside",
            "related_products": [],
            "version": "unknown",
        }
    ]

    mapping = get_nuclei_product_mapping()

    mapping["nuclei_citrix_adc_gateway_panel"][0]["product"] = 1
    mapping["nuclei_citrix_adc_gateway_panel"][0]["related_products"][0]["product"] = 2
    mapping["nuclei_netscaler_aaa_login"][0]["product"] = 2

    assert mapping == {
        "nuclei_citrix_adc_gateway_panel": [
            {
                "product": 1,
                "related_products": [
                    {
                        "product": 2,
                        "related_products": [],
                        "relationship": "something-something-something-darkside",
                        "version": "unknown",
                    }
                ],
                "version": "unknown",
            }
        ],
        "nuclei_netscaler_aaa_login": [{"product": 2, "related_products": [], "version": "unknown"}],
    }


def test_prevent_circular_references(db, reset_time_cache):
    create_test_product_data()

    product = Product.objects.all().first()
    relationship = ProductRelationship.objects.all().first()

    # create circular reference:
    ProductHierarchy.objects.create(product=product, related_product=product, relationship=relationship)

    # retrieving the data should not give an error, it will just stop in depth
    assert get_nested_products_in_an_inefficient_way(product)

    with pytest.raises(ValueError):
        get_nested_products_in_an_inefficient_way(product, 400)


sample_product_tree = {
    "product": 1,
    "version": "unknown",
    "related_products": [
        {
            "product": 2,
            "relationship": "something",
            "version": "unknown",
            "related_products": [
                {
                    "product": 3,
                    "relationship": "something-something",
                    "version": "unknown",
                    "related_products": [
                        {
                            "product": 4,
                            "relationship": "something-something-something-darkside",
                            "version": "unknown",
                            "related_products": [],
                        },
                        {
                            "product": 5,
                            "relationship": "something-something-something-more-darkside",
                            "version": "unknown",
                            "related_products": [],
                        },
                    ],
                }
            ],
        }
    ],
}


def test_set_value_to_tech_in_tree(reset_time_cache):
    product_tree = copy.deepcopy(sample_product_tree)

    # change nothing:
    unaltered = copy.deepcopy(sample_product_tree)
    set_value_to_tech_in_tree(product_tree, product_id=100, my_property="version", value="1.2.3")
    assert product_tree == unaltered

    set_value_to_tech_in_tree(product_tree, product_id=1, my_property="version", value="1.2.3")
    set_value_to_tech_in_tree(product_tree, product_id=2, my_property="version", value="2.3.4")
    set_value_to_tech_in_tree(product_tree, product_id=3, my_property="version", value="3.2.1")
    set_value_to_tech_in_tree(product_tree, product_id=4, my_property="version", value="4.3.2")
    set_value_to_tech_in_tree(product_tree, product_id=5, my_property="version", value="5.4.3")

    assert product_tree == {
        "product": 1,
        "version": "1.2.3",
        "related_products": [
            {
                "product": 2,
                "relationship": "something",
                "version": "2.3.4",
                "related_products": [
                    {
                        "product": 3,
                        "relationship": "something-something",
                        "version": "3.2.1",
                        "related_products": [
                            {
                                "product": 4,
                                "relationship": "something-something-something-darkside",
                                "version": "4.3.2",
                                "related_products": [],
                            },
                            {
                                "product": 5,
                                "relationship": "something-something-something-more-darkside",
                                "version": "5.4.3",
                                "related_products": [],
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_smash_tree():
    product_tree = copy.deepcopy(sample_product_tree)

    assert smash_tree(product_tree) == [
        {"product": 1, "version": "unknown"},
        {"product": 2, "version": "unknown"},
        {"product": 3, "version": "unknown"},
        {"product": 4, "version": "unknown"},
        {"product": 5, "version": "unknown"},
    ]


def test_smash_trees():
    product_tree1 = copy.deepcopy(sample_product_tree)
    product_tree2 = copy.deepcopy(sample_product_tree)

    assert smash_trees([product_tree1, product_tree2]) == [
        {"product": 1, "version": "unknown"},
        {"product": 2, "version": "unknown"},
        {"product": 3, "version": "unknown"},
        {"product": 4, "version": "unknown"},
        {"product": 5, "version": "unknown"},
    ]


def test_prioritize_tech():
    assert [{1: 1}, {2: 2}] != [{2: 2}, {1: 1}]

    list_of_techs = [{"product": 1, "version": "1.1.1"}, {"product": 2, "version": "2.2.2"}]

    assert prioritize_tech(list_of_techs, 1) == list_of_techs

    assert prioritize_tech(list_of_techs, 2) == [{"product": 2, "version": "2.2.2"}, {"product": 1, "version": "1.1.1"}]

    assert prioritize_tech(list_of_techs, 2) != list_of_techs

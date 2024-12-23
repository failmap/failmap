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
    generated_login_portal_meaning_data,
    create_loging_plaza_meanings_for_scans_per_scan,
    get_tech_for_endpoints,
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


def test_generated_login_portal_meaning_data(db, reset_time_cache):
    # monkey patch the time cache, otherwise the test will fail due to cached stuff
    # make sure to use the time_cache from login_plaza(!)
    # this does not work, so we set freeze_time on this test to make sure the cache is expiredf.
    # time_cache.cache_set("login_plaza_product_mapping", {})
    # also freeze_time does not work. for some reason. So better rewrite time cache to do what it supposed to.

    # the problem was that the prioritized tech did not appear and that the order of the techs was random
    # and therefore a new meaning was generated each time, resulting a new database record.
    now = datetime.now(timezone.utc)
    url = Url.objects.all().create(url="test.nl", created_on=now, is_dead=False, not_resolvable=False)
    url.save()
    endpoint = Endpoint.objects.create(url=url, port=443, protocol="https")

    evidence = [
        {
            "template-id": "wordpress-login",
            "name": "wordpress login panel - detect",
            "finding-name": "nuclei_wordpress_login",
            "evidence": {
                # usually the version number
                "extracted-results": [],
                "matched-at": "https://www.bezoekerscentrum.rijkswaterstaat.nl:443/wp-login.php",
            },
        }
    ]

    # make sure there is a nice product tree for wordpress, php and some other related techs.

    # make the example hierarchy:
    # wordpress -> php -> c
    c_vendor = ProductVendor.objects.create(name="c-company")
    c_goal = ProductGoal.objects.create(name="c-ing")
    c_product = Product.objects.create(
        name="C",
        vendor=c_vendor,
        goal=c_goal,
        intended_use_case_description="something",
        is_open_source=True,
        common_execution_environment="Server",
        is_irrelevant=False,
    )

    p_vendor = ProductVendor.objects.create(name="php-company")
    p_goal = ProductGoal.objects.create(name="php-ing")
    p_product = Product.objects.create(
        name="PHP",
        vendor=p_vendor,
        goal=p_goal,
        intended_use_case_description="something",
        is_open_source=True,
        common_execution_environment="Server",
        is_irrelevant=False,
    )

    w_vendor = ProductVendor.objects.create(name="wordpress-company")
    w_goal = ProductGoal.objects.create(name="wordpress-ing")
    w_product = Product.objects.create(
        name="Wordpress",
        vendor=w_vendor,
        goal=w_goal,
        intended_use_case_description="something",
        is_open_source=True,
        common_execution_environment="Server",
        is_irrelevant=False,
    )

    finding_1 = ScannerFinding.objects.create(name="nuclei_wordpress_login")
    w_product.scanner_finding_name_mapping.add(finding_1)

    relationship = ProductRelationship.objects.create(name="is written in")
    # onderwerp, leidend voorwerp / subject, object
    ProductHierarchy.objects.create(product=w_product, related_product=p_product, relationship=relationship)
    ProductHierarchy.objects.create(product=p_product, related_product=c_product, relationship=relationship)

    assert Product.objects.count() == 3
    assert ProductHierarchy.objects.count() == 2

    # see if the hierarchy has been stored correctly.
    # make sure the cacheing is gone from the get_nested_products_in_an_inefficient_way method, othrewise youll
    # get old stuff: This method is added via the TTLCache stuff.
    get_nested_products_in_an_inefficient_way.cache_clear()

    nuclei_product_mapping = get_nuclei_product_mapping(use_cache=False)
    sample_product_tree = [
        {
            "product": w_product.id,
            "related_products": [
                {
                    "product": p_product.id,
                    "related_products": [
                        {
                            "product": c_product.id,
                            "related_products": [],
                            "relationship": "is-written-in",
                            "version": "unknown",
                        },
                    ],
                    "relationship": "is-written-in",
                    "version": "unknown",
                },
            ],
            "version": "unknown",
        },
    ]

    assert nuclei_product_mapping == {"nuclei_wordpress_login": sample_product_tree}

    # this is a weakness in the portal scanning, it uses 'get tech' which is based on the currently available
    # tech that is in the database. If there is none, there will be no techs. Therefore if the tech is stored
    # _after_ the login portal is stored, this will be one record behind the portal.
    # --- this order might have been correctly... todo: check if the order of storage is correct.
    # -- todo: perhaps this is not really relevant. But make sure that tech is in the same order.

    # add some technologies and apparently also the previous portals... this cannot be right in this context.
    # but let's not rework the architecture and go with the flow. This will cause issues though as old data is reused.
    # before storing the new one...

    # both use the sample wordpress finding-name, this should result in a unique tree, even though there are multiple
    # hits. Other products are not matched and thus no tree is created for them.
    EndpointGenericScan.objects.create(
        is_the_latest_scan=True,
        rating_determined_on=now,
        endpoint=endpoint,
        type="nuclei_exposed_panels",
        evidence="""[{"template-id": "plesk-onyx-login", "name": "plesk login panel - detect", "finding-name": "nuclei_wordpress_login", "evidence": {"extracted-results": [], "matched-at": "https://mail.nieuwegeinsewijken.nl/login_up.php"}}]""",  # noqa
    )

    EndpointGenericScan.objects.create(
        is_the_latest_scan=True,
        rating_determined_on=now,
        endpoint=endpoint,
        type="nuclei_technologies",
        evidence="""[{"template-id": "tech-detect", "name": "wappalyzer technology detection", "finding-name": "nuclei_wordpress_login", "evidence": {"extracted-results": [], "matched-at": "https://www.bezoekerscentrum.rijkswaterstaat.nl:443"}}, {"template-id": "waf-detect", "name": "waf detection", "finding-name": "nuclei_waf_detect_nginxgeneric", "evidence": {"extracted-results": [], "matched-at": "https://www.bezoekerscentrum.rijkswaterstaat.nl:443"}}, {"template-id": "wordpress-contact-form-7", "name": "contact form 7 detection", "finding-name": "nuclei_wordpress_contact_form_7_outdated_version", "evidence": {"extracted-results": ["5.9.8"], "matched-at": "https://www.bezoekerscentrum.rijkswaterstaat.nl:443/wp-content/plugins/contact-form-7/readme.txt"}}, {"template-id": "wordpress-cookie-notice", "name": "cookie notice & compliance for gdpr / ccpa detection", "finding-name": "nuclei_wordpress_cookie_notice", "evidence": {"extracted-results": ["2.4.18"], "matched-at": "https://www.bezoekerscentrum.rijkswaterstaat.nl:443/wp-content/plugins/cookie-notice/readme.txt"}}, {"template-id": "wordpress-detect", "name": "wordpress detect", "finding-name": "nuclei_wordpress_detect", "evidence": {"extracted-results": [], "matched-at": "https://bezoekerscentrum.rijkswaterstaat.nl/schipholamsterdamalmere/"}}, {"template-id": "wordpress-really-simple-ssl", "name": "really simple security \u2013 simple and performant security (formerly really simple ssl) detection", "finding-name": "nuclei_wordpress_really_simple_ssl", "evidence": {"extracted-results": ["9.1.2"], "matched-at": "https://www.bezoekerscentrum.rijkswaterstaat.nl:443/wp-content/plugins/really-simple-ssl/readme.txt"}}, {"template-id": "wordpress-w3-total-cache", "name": "w3 total cache detection", "finding-name": "nuclei_wordpress_w3_total_cache_outdated_version", "evidence": {"extracted-results": ["2.7.6"], "matched-at": "https://www.bezoekerscentrum.rijkswaterstaat.nl:443/wp-content/plugins/w3-total-cache/readme.txt"}}, {"template-id": "wordpress-wordpress-seo", "name": "yoast seo detection", "finding-name": "nuclei_wordpress_wordpress_seo_outdated_version", "evidence": {"extracted-results": ["23.6"], "matched-at": "https://www.bezoekerscentrum.rijkswaterstaat.nl:443/wp-content/plugins/wordpress-seo/readme.txt"}}]""",  # noqa
    )
    tech = get_tech_for_endpoints([endpoint.id])
    assert tech == {endpoint.id: sample_product_tree}

    # changing the order of the scans should not impact techs.
    create_loging_plaza_meanings_for_scans_per_scan(evidence[0], endpoint.id, tech, nuclei_product_mapping)

    # this should have techs which are consistent over each call...
    meaning = generated_login_portal_meaning_data(evidence, endpoint.id)

    # the meaning should be consistent per portal and the wordpress product should be the first one...
    assert meaning == [
        {
            "portal_extracted": [],
            "portal_name": "wordpress login panel - detect",
            "portal_url": "https://www.bezoekerscentrum.rijkswaterstaat.nl:443/wp-login.php",
            "tech": [
                {
                    "product": w_product.id,
                    "version": "unknown",
                },
                # sorted by id:
                {
                    "product": c_product.id,
                    "version": "unknown",
                },
                {
                    "product": p_product.id,
                    "version": "unknown",
                },
            ],
        },
    ]

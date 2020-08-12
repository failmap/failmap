from datetime import datetime

import pytz

from websecmap.reporting.models import UrlReport
from websecmap.reporting.report import create_timeline, create_url_report
from websecmap.scanners.models import EndpointGenericScan
from websecmap.scanners.tests.test_plannedscan import create_endpoint, create_url


def test_data_from_dead_endpoint_stays_gone(db):
    """
    Scenario:

    It's March 1st 2020 (or later). Example.nl has an endpoint that is dead, and one that is alive. A scan
    has been performed and stored on both endpoints. When creating an url report, we don't want
    to see the scan result from the dead endpoint in the report, after it died.
    """

    u = create_url("example.nl")
    e1 = create_endpoint(u, 4, "https", 443)

    # would e2 be on the same moment, this would result in a repeated finding (which is also wrong).
    e2 = create_endpoint(u, 6, "https", 443)

    # e2 died on the 20th of january:
    e2.is_dead_since = datetime(2020, 1, 20)
    e2.is_dead = True
    e2.save()

    # make identical scans for both endpoints. But one endpoint dies, and the other doesn't.

    epgs1 = EndpointGenericScan()
    epgs1.endpoint = e1
    epgs1.rating = "F"
    epgs1.last_scan_moment = datetime(2020, 1, 5)
    epgs1.type = "tls_qualys_encryption_quality"
    epgs1.rating_determined_on = datetime(2020, 1, 5)
    epgs1.save()

    epgs2 = EndpointGenericScan()
    epgs2.endpoint = e1
    epgs2.rating = "A"
    epgs2.last_scan_moment = datetime(2020, 2, 5)
    epgs2.type = "tls_qualys_encryption_quality"
    epgs2.rating_determined_on = datetime(2020, 2, 5)
    epgs2.save()

    epgs3 = EndpointGenericScan()
    epgs3.endpoint = e2
    epgs3.rating = "F"
    epgs3.last_scan_moment = datetime(2020, 1, 6)
    epgs3.type = "tls_qualys_encryption_quality"
    epgs3.rating_determined_on = datetime(2020, 1, 6)
    epgs3.save()

    epgs4 = EndpointGenericScan()
    epgs4.endpoint = e2
    epgs4.rating = "A"
    epgs4.last_scan_moment = datetime(2020, 2, 6)
    epgs4.type = "tls_qualys_encryption_quality"
    epgs4.rating_determined_on = datetime(2020, 2, 6)
    epgs4.save()

    # extra action, to see if this is picked up, while the previous one is ignored.
    epgs5 = EndpointGenericScan()
    epgs5.endpoint = e1
    epgs5.rating = "A+"
    epgs5.last_scan_moment = datetime(2020, 2, 7)
    epgs5.type = "tls_qualys_encryption_quality"
    epgs5.rating_determined_on = datetime(2020, 2, 7)
    epgs5.save()

    assert EndpointGenericScan.objects.count() == 5

    # the timeline matches the above scenario: scnas from the 5th and 6th of january are seen, then the
    # endpoint 2 dies, then scans from the 5th and 6th of february are seen.
    print(create_timeline(u))
    assert create_timeline(u) == {
        datetime(2020, 1, 5, 0, 0, 59, 999999, tzinfo=pytz.utc): {
            'dead_endpoints': [], 'endpoints': [e1], 'endpoint_scans': [epgs1], 'url_scans': [], 'urls': [],
            'endpoint_scan': {'scans': [epgs1], 'endpoints': [e1]}
        },
        datetime(2020, 1, 6, 0, 0, 59, 999999, tzinfo=pytz.utc): {
            'dead_endpoints': [], 'endpoints': [e2], 'endpoint_scans': [epgs3], 'url_scans': [], 'urls': [],
            'endpoint_scan': {'scans': [epgs3], 'endpoints': [e2]}
        },
        # where are the scans on january fifth?
        datetime(2020, 1, 20, 0, 0, 59, 999999, tzinfo=pytz.utc): {
            'dead': True, 'dead_endpoints': [e2], 'endpoint_scans': [], 'endpoints': [], 'url_scans': [],
            'urls': []
        },
        datetime(2020, 2, 5, 0, 0, 59, 999999, tzinfo=pytz.utc): {
            'dead_endpoints': [], 'endpoints': [e1], 'endpoint_scans': [epgs2], 'url_scans': [], 'urls': [],
            'endpoint_scan': {'scans': [epgs2], 'endpoints': [e1]}
        },
        # here we see that endpoint two is (correctly) returned, as something actually happened on endpoint two.
        # in terms of timelines this is correct. But we don't want to see this in the report because the
        # endpoint died.
        # This should not cause a repeated finding: as this
        datetime(2020, 2, 6, 0, 0, 59, 999999, tzinfo=pytz.utc): {
            'dead_endpoints': [], 'endpoints': [e2], 'endpoint_scans': [epgs4], 'url_scans': [], 'urls': [],
            'endpoint_scan': {'scans': [epgs4], 'endpoints': [e2]}
        },

        # add another thing, so to see if the reporting still works, even if one endpoint is skipped due to
        # being deleted.
        datetime(2020, 2, 7, 0, 0, 59, 999999, tzinfo=pytz.utc): {
            'dead_endpoints': [], 'endpoints': [e1], 'endpoint_scans': [epgs5], 'url_scans': [], 'urls': [],
            'endpoint_scan': {'scans': [epgs5], 'endpoints': [e1]}
        },
    }

    # now create the report based on the above data.
    create_url_report(create_timeline(u), u)

    # reports from the various days things happened:
    assert UrlReport.objects.all().count() == 6

    # We should NOT see any scan results from e2 in the url report after datetime(2020, 1, 20)...
    fourth_report = UrlReport.objects.get(id=4)

    # here we see that the report is returned, and that data from endpoint 2 should not be in the report
    # anymore. It will contain the one scan from 5 february, will be here.
    assert len(fourth_report.calculation['endpoints']) == 1
    assert len(fourth_report.calculation['endpoints'][0]['ratings']) == 1
    assert fourth_report.calculation['endpoints'][0]['ratings'][0]['since'] == "2020-02-05T00:00:00+00:00"
    # last scan has auto_now add behaviour, that should be removed as that leads to inconsistencies.
    # assert second_to_last_report.calculation['endpoints'][0]['ratings'][0]['last_scan'] == str(datetime(2020, 2, 5))

    del(fourth_report.calculation['endpoints'][0]['ratings'][0]['last_scan'])

    assert fourth_report.calculation == {
        'endpoint_issues_high': 0,
        'endpoint_issues_low': 0,
        'endpoint_issues_medium': 0,
        'endpoints': [{'concat': 'https/443 IPv4',
                       'explained_high': 0,
                       'explained_low': 0,
                       'explained_medium': 0,
                       'high': 0,
                       'id': e1.id,
                       'ip': 4,
                       'ip_version': 4,
                       'low': 0,
                       'medium': 0,
                       'ok': 1,
                       'port': 443,
                       'protocol': 'https',
                       'ratings': [{'comply_or_explain_explained_on': '',
                                    'comply_or_explain_explanation': '',
                                    'comply_or_explain_explanation_valid_until': '',
                                    'comply_or_explain_valid_at_time_of_report': False,
                                    'error_in_test': False,
                                    'explanation': 'Good Transport Security, rated A.',
                                    'high': 0,
                                    'is_explained': False,
                                    'low': 0,
                                    'medium': 0,
                                    'not_applicable': False,
                                    'not_testable': False,
                                    'ok': 1,
                                    'scan': 2,
                                    'scan_type': 'tls_qualys_encryption_quality',
                                    'since': '2020-02-05T00:00:00+00:00',
                                    'type': 'tls_qualys_encryption_quality'}],
                       'v4': True}],
        'explained_endpoint_issues_high': 0,
        'explained_endpoint_issues_low': 0,
        'explained_endpoint_issues_medium': 0,
        'explained_high': 0,
        'explained_high_endpoints': 0,
        'explained_low': 0,
        'explained_low_endpoints': 0,
        'explained_medium': 0,
        'explained_medium_endpoints': 0,
        'explained_total_endpoint_issues': 0,
        'explained_total_issues': 0,
        'explained_total_url_issues': 0,
        'explained_url_issues_high': 0,
        'explained_url_issues_low': 0,
        'explained_url_issues_medium': 0,
        'high': 0,
        'high_endpoints': 0,
        'low': 0,
        'low_endpoints': 0,
        'medium': 0,
        'medium_endpoints': 0,
        'ok': 1,
        'ok_endpoints': 1,
        'ratings': [],
        'total_endpoint_issues': 0,
        'total_endpoints': 1,
        'total_issues': 0,
        'total_url_issues': 0,
        'url': 'example.nl',
        'url_issues_high': 0,
        'url_issues_low': 0,
        'url_issues_medium': 0,
        'url_ok': 1}

    # in the last report, where a scan on endpoint 2 happened, it will be ignored (the scan is ignored because the
    # endpoint is dead).

    fifth_report = UrlReport.objects.get(id=5)
    # the calculation should not have changed, as the new endpoint does nothing:
    del fifth_report.calculation['endpoints'][0]['ratings'][0]['last_scan']
    # pprint(fifth_report.calculation)

    assert len(fifth_report.calculation['endpoints']) == 1
    assert len(fifth_report.calculation['endpoints'][0]['ratings']) == 1
    assert fifth_report.calculation['endpoints'][0]['ratings'][0]['since'] == "2020-02-05T00:00:00+00:00"

    assert fourth_report.calculation == fifth_report.calculation

    sixth_report = UrlReport.objects.get(id=6)
    del sixth_report.calculation['endpoints'][0]['ratings'][0]['last_scan']

    # only the date of the scan has changed.
    assert sixth_report.calculation == {
        'endpoint_issues_high': 0,
        'endpoint_issues_low': 0,
        'endpoint_issues_medium': 0,
        'endpoints': [{'concat': 'https/443 IPv4',
                       'explained_high': 0,
                       'explained_low': 0,
                       'explained_medium': 0,
                       'high': 0,
                       'id': e1.id,
                       'ip': 4,
                       'ip_version': 4,
                       'low': 0,
                       'medium': 0,
                       'ok': 1,
                       'port': 443,
                       'protocol': 'https',
                       'ratings': [{'comply_or_explain_explained_on': '',
                                    'comply_or_explain_explanation': '',
                                    'comply_or_explain_explanation_valid_until': '',
                                    'comply_or_explain_valid_at_time_of_report': False,
                                    'error_in_test': False,
                                    'explanation': 'Perfect Transport Security, rated A+.',
                                    'high': 0,
                                    'is_explained': False,
                                    'low': 0,
                                    'medium': 0,
                                    'not_applicable': False,
                                    'not_testable': False,
                                    'ok': 1,
                                    'scan': 5,
                                    'scan_type': 'tls_qualys_encryption_quality',
                                    'since': '2020-02-07T00:00:00+00:00',
                                    'type': 'tls_qualys_encryption_quality'}],
                       'v4': True}],
        'explained_endpoint_issues_high': 0,
        'explained_endpoint_issues_low': 0,
        'explained_endpoint_issues_medium': 0,
        'explained_high': 0,
        'explained_high_endpoints': 0,
        'explained_low': 0,
        'explained_low_endpoints': 0,
        'explained_medium': 0,
        'explained_medium_endpoints': 0,
        'explained_total_endpoint_issues': 0,
        'explained_total_issues': 0,
        'explained_total_url_issues': 0,
        'explained_url_issues_high': 0,
        'explained_url_issues_low': 0,
        'explained_url_issues_medium': 0,
        'high': 0,
        'high_endpoints': 0,
        'low': 0,
        'low_endpoints': 0,
        'medium': 0,
        'medium_endpoints': 0,
        'ok': 1,
        'ok_endpoints': 1,
        'ratings': [],
        'total_endpoint_issues': 0,
        'total_endpoints': 1,
        'total_issues': 0,
        'total_url_issues': 0,
        'url': 'example.nl',
        'url_issues_high': 0,
        'url_issues_low': 0,
        'url_issues_medium': 0,
        'url_ok': 1}

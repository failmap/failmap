from websecmap.organizations.models import Url
from datetime import datetime
import pytz

from websecmap.reporting.models import UrlReport
from websecmap.reporting.report import create_timeline, create_url_report
from websecmap.scanners.models import Endpoint, EndpointGenericScan


def test_url_report(db):
    # Url test.nl has been created
    day_0 = datetime(day=1, month=1, year=2000, tzinfo=pytz.utc)
    # First endpoint was created, first OK scan
    day_1 = datetime(day=2, month=1, year=2000, tzinfo=pytz.utc)
    # Previous scan was now a High.
    day_2 = datetime(day=3, month=1, year=2000, tzinfo=pytz.utc)
    day_3 = datetime(day=4, month=1, year=2000, tzinfo=pytz.utc)
    day_4 = datetime(day=5, month=1, year=2000, tzinfo=pytz.utc)
    day_5 = datetime(day=6, month=1, year=2000, tzinfo=pytz.utc)
    day_6 = datetime(day=7, month=1, year=2000, tzinfo=pytz.utc)
    day_7 = datetime(day=8, month=1, year=2000, tzinfo=pytz.utc)
    day_8 = datetime(day=9, month=1, year=2000, tzinfo=pytz.utc)
    # Url test.nl could not be found anymore
    day_9 = datetime(day=10, month=1, year=2000, tzinfo=pytz.utc)
    url, created = Url.objects.all().get_or_create(url='test.nl', created_on=day_0, not_resolvable=False)

    # a standard HTTPS endpoint
    first_endpoint, created = Endpoint.objects.all().get_or_create(
        url=url, protocol='https', port='443', ip_version=4, discovered_on=day_1, is_dead=False)

    perfect_scan, created = EndpointGenericScan.objects.all().get_or_create(
        endpoint=first_endpoint, type='tls_qualys_encryption_quality', rating='A+', rating_determined_on=day_1,
        last_scan_moment=day_1, comply_or_explain_is_explained=False, is_the_latest_scan=True)

    UrlReport.objects.all().delete()
    create_url_report(create_timeline(url), url)

    # We've created a report for 1 day.
    count = UrlReport.objects.all().count()
    assert count == 1

    # the report has one endpoint, and it's ok.
    report = UrlReport.objects.all().first()
    assert report.total_endpoints == 1
    assert report.ok == 1

    # on day two the rating changes to something that's not correct. This results in another report being generated.
    # now we have two reports, and the last one has a high rating. We're not testing the scanner, we are testing
    # if the additional report is generated.

    perfect_scan.is_the_latest_scan = False
    perfect_scan.save()

    error_scan, created = EndpointGenericScan.objects.all().get_or_create(
        endpoint=first_endpoint, type='tls_qualys_encryption_quality', rating='F', rating_determined_on=day_2,
        last_scan_moment=day_2, comply_or_explain_is_explained=False, is_the_latest_scan=True)

    # We always rebuild the entire set of reports, as it's crazy fast.
    UrlReport.objects.all().delete()
    create_url_report(create_timeline(url), url)

    count = UrlReport.objects.all().count()
    assert count == 2

    report = UrlReport.objects.all().order_by('pk').last()
    assert report.total_endpoints == 1
    # make sure that the endpoints are actually there.
    assert len(report.calculation['endpoints']) == 1
    assert report.ok == 0
    assert report.high == 1

    # on day 3 the url becomes non resolvable. This means that the url + endpoints will be removed from the report
    # as it is not relevant anymore. The previous reports will be saved, and a third one will be generated where
    # endpoints will be empty.

    url.not_resolvable = True
    url.not_resolvable_since = day_3
    url.save()

    UrlReport.objects.all().delete()
    create_url_report(create_timeline(url), url)

    count = UrlReport.objects.all().count()
    assert count == 3

    report = UrlReport.objects.all().order_by('pk').last()
    assert report.total_endpoints == 0
    assert report.calculation['ratings'] == []
    assert report.calculation['endpoints'] == []
    # Check that some statistics have been generated
    assert report.calculation['high'] == 0
    assert report.high == 0
    assert report.ok == 0

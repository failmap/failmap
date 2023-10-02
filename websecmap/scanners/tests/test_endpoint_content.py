from datetime import date, datetime, timezone

from websecmap.organizations.models import Url
from websecmap.scanners.models import HttpEndpointContent, Endpoint
from websecmap.scanners.scanner.endpoint_content import content_is_identical, compare_and_clean_previous_site_copies


def test_content_is_identical():
    assert content_is_identical("basisbeveiliging", "") is False
    assert content_is_identical("basisbeveiliging", "basisbeveiliging") is True
    # typo in the last string, its 93% the same, so >90
    assert content_is_identical("basisbeveiliging", "basisbeveiliginn", 90) is True

    # now with real website content
    content_1 = """
    <!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="content-type" content="text/html;
    charset=UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,shrink-to-fit=no"><meta name=
    "generator" content="Web Security Map by the Internet Cleanup Foundation"><link rel="stylesheet" id="custom-st
    yles"/><base href="./"/><link id="favicon-apple-touch-icon" rel="apple-touch-icon" sizes="180x180" href="//app
    le-touch-icon.png"><link id="favicon-icon-small" rel="icon" type="image/png" sizes="32x32" href="//favicon-32x
    32.png"><link id="favicon-icon-large" rel="icon" type="image/png" sizes="16x16" href="//favicon-16x16.png"><li
    nk id="favicon-manifest" rel="manifest" href="//site.webmanifest"><link id="favicon-mask-icon" rel="mask-icon"
     href="//safari-pinned-tab.svg" color="#5bbad5"><meta name="msapplication-TileColor" content="#da532c"><meta n
    ame="theme-color" content="#ffffff"><title>Loading map...</title><script defer="defer" src="/js/chunk-vendors.
    844dd49f.js"></script><script defer="defer" src="/js/app.147c35b8.js"></script><link href="/css/chunk-vendors.
    c25b230b.css" rel="stylesheet"><link href="/css/app.222f28b0.css" rel="stylesheet"></head><body style="backgro
    und-color: var(--dark);"><noscript><strong>We're sorry but Loading map... doesn't work properly without JavaSc
    ript enabled. Please enable it to continue.</strong></noscript><div id="app"></div></body></html>
    """

    # some content changes:
    content_2 = """
    <!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="content-type" content="text/html;
    charset=UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,shrink-to-fit=no"><meta name=
    "generator" content="Basisbeveiliging by the Internet Cleanup Foundation"><link rel="stylesheet" id="custom-st
    yles"/><base href="./"/><link id="favicon-apple-touch-icon" rel="apple-touch-icon" sizes="180x180" href="//app
    le-touch-icon.png"><link id="favicon-icon-small" rel="icon" type="image/png" sizes="32x32" href="//favicon-32x
    32.png"><link id="favicon-icon-large" rel="icon" type="image/png" sizes="16x16" href="//favicon-16x16.png"><li
    nk id="favicon-manifest" rel="manifest" href="//site.webmanifest"><link id="favicon-mask-icon" rel="mask-icon"
     href="//safari-pinned-tab.svg" color="#5bbad5"><meta name="msapplication-TileColor" content="#da532c"><meta n
    ame="theme-color" content="#ffffff"><title>Loading map...</title><script defer="defer" src="/js/chunk-vendors.
    844dd49f.js"></script><script defer="defer" src="/js/app.147c35b8.js"></script><link href="/css/chunk-vendors.
    c25b230b.css" rel="stylesheet"><link href="/css/app.222f28b0.css" rel="stylesheet"></head><body style="backgro
    und-color: var(--dark);"><noscript><strong>We're sorry but Loading map... doesn't work properly without JavaSc
    ript enabled. Please enable it to continue.</strong></noscript><div id="app"></div></body></html>
    """
    # 98.92 similarity.
    assert content_is_identical(content_1, content_2, 98) is True


def test_compare_and_clean_previous_site_copies(db):
    # nothing in db, nothing happens:
    compare_and_clean_previous_site_copies()

    # a few scans on different endpoints, nothing happens
    url = Url.objects.create(url="example.nl")
    ep = Endpoint.objects.create(url=url, port=80, protocol="http")
    ep2 = Endpoint.objects.create(url=url, port=80, protocol="http")
    HttpEndpointContent.objects.create(endpoint=ep, content="1234", is_the_latest=True, at_when=date(2015, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=True, at_when=date(2015, 1, 1))
    compare_and_clean_previous_site_copies()
    assert HttpEndpointContent.objects.all().count() == 2

    # now add some older scan results to each endpoint with the same content, then clean it up:
    # the original content now has an at_when since 2014
    HttpEndpointContent.objects.create(endpoint=ep, content="1234", is_the_latest=False, at_when=date(2014, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2014, 1, 1))
    assert HttpEndpointContent.objects.all().count() == 4
    compare_and_clean_previous_site_copies()
    assert HttpEndpointContent.objects.all().count() == 2
    assert HttpEndpointContent.objects.all().first().at_when == datetime(2014, 1, 1, tzinfo=timezone.utc)

    # now add a scan with different content and a scan before that with the same content. as there was a change
    # in between both scans stay.
    HttpEndpointContent.objects.create(endpoint=ep, content="5678", is_the_latest=False, at_when=date(2014, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep, content="1324", is_the_latest=False, at_when=date(2013, 1, 1))
    compare_and_clean_previous_site_copies()
    assert HttpEndpointContent.objects.all().count() == 4

    # now add a bunch of the same scans and see if they are all cleaned up
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2014, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2013, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2012, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2011, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2010, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2009, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2008, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2007, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2006, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2005, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2004, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2003, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2002, 1, 1))
    HttpEndpointContent.objects.create(endpoint=ep2, content="1234", is_the_latest=False, at_when=date(2001, 1, 1))
    assert HttpEndpointContent.objects.all().count() == 18

    # you'll have to call this a few time as each scan only checks one previous scan
    compare_and_clean_previous_site_copies()
    compare_and_clean_previous_site_copies()
    compare_and_clean_previous_site_copies()
    compare_and_clean_previous_site_copies()
    assert HttpEndpointContent.objects.all().count() == 4

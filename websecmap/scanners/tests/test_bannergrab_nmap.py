from datetime import datetime

import pytz

from websecmap.organizations.models import Url
from websecmap.scanners.models import UrlIp, EndpointGenericScan
from websecmap.scanners.scanner.bannergrab_nmap import store_results
from websecmap.scanners.scanner.banners.detect_version import re_evaluate_bannergrab_versions

generic_data = {
    "hostnames": [
        {"name": "basisbeveiliging.nl", "type": "user"},
        {"name": "basisbevprod01.cobytes.io", "type": "PTR"},
    ],
    "addresses": {"ipv4": "185.71.61.127"},
    "vendor": {},
    "status": {"state": "up", "reason": "syn-ack"},
}


def test_store_nmap_results(db):

    results = {
        **generic_data,
        **{
            "tcp": {
                22: {
                    "state": "open",
                    "reason": "syn-ack",
                    "name": "ssh",
                    "product": "OpenSSH",
                    "version": "7.6p1 Ubuntu 4ubuntu0.5",
                    "extrainfo": "Ubuntu Linux; protocol 2.0",
                    "conf": "10",
                    "cpe": "cpe:/o:linux:linux_kernel",
                    "script": {"banner": "SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5"},
                },
                80: {
                    "state": "open",
                    "reason": "syn-ack",
                    "name": "http",
                    "product": "nginx",
                    "version": "",
                    "extrainfo": "",
                    "conf": "10",
                    "cpe": "cpe:/a:igor_sysoev:nginx",
                },
                443: {
                    "state": "open",
                    "reason": "syn-ack",
                    "name": "http",
                    "product": "nginx",
                    "version": "",
                    "extrainfo": "",
                    "conf": "10",
                    "cpe": "cpe:/a:igor_sysoev:nginx",
                },
            }
        },
    }

    # nothing is stored, as there are no endpoints to store this to
    store_results("127.0.0.1", results)

    url = Url.objects.create(url="internetcleanup.foundation")
    UrlIp.objects.create(url=url, ip="127.0.0.1", is_v4=True, discovered_on=datetime.now(pytz.utc))

    # first moment something is stored.
    store_results("127.0.0.1", results)

    # expectation:
    # ssh/22: product, version, extrainfo, banner, cpe
    # http/80: product, cpe
    # http:/443: product + cpe
    # reconstructing a banner from porduct and version when there is no banner. So nginx and nginx.
    assert EndpointGenericScan.objects.all().count() == 11

    # let's remove two ports, this should be cleaned up
    results = {
        **generic_data,
        **{
            "tcp": {
                22: {
                    "state": "open",
                    "reason": "syn-ack",
                    "name": "ssh",
                    "product": "OpenSSH",
                    "version": "7.6p1 Ubuntu 4ubuntu0.5",
                    "extrainfo": "Ubuntu Linux; protocol 2.0",
                    "conf": "10",
                    "cpe": "cpe:/o:linux:linux_kernel",
                    "script": {"banner": "SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5"},
                }
            }
        },
    }
    store_results("127.0.0.1", results)

    # the cleaning consists out of the existing 9 results. And the four results from 80 and 443 scrubbed.
    assert EndpointGenericScan.objects.all().count() == 17  # 9 + 4

    # nothing changes if we add the same results again
    store_results("127.0.0.1", results)
    store_results("127.0.0.1", results)
    store_results("127.0.0.1", results)
    assert EndpointGenericScan.objects.all().count() == 17  # 9 + 4

    # let's change a cpe, product, version, extraninfo and banner on 443: this will add these 5 new values:
    results = {
        **generic_data,
        **{
            "tcp": {
                22: {
                    "state": "open",
                    "reason": "syn-ack",
                    "name": "ssh",
                    "product": "altered_OpenSSH",
                    "version": "altered_7.6p1 Ubuntu 4ubuntu0.5",
                    "extrainfo": "altered_Ubuntu Linux; protocol 2.0",
                    "conf": "10",
                    "cpe": "altered_cpe:/o:linux:linux_kernel",
                    "script": {"banner": "altered_SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5"},
                },
            }
        },
    }
    store_results("127.0.0.1", results)
    assert EndpointGenericScan.objects.all().count() == 22  # 13 existing + 5 new ones

    # let's remove a cpe on 443: this will add 1 record with the new cpe value (empty)
    # empty is only added if there was a result in the past.
    results = {
        **generic_data,
        **{
            "tcp": {
                22: {
                    "state": "open",
                    "reason": "syn-ack",
                    "name": "ssh",
                    "product": "altered_OpenSSH",
                    "version": "altered_7.6p1 Ubuntu 4ubuntu0.5",
                    "extrainfo": "altered_Ubuntu Linux; protocol 2.0",
                    "conf": "10",
                    "cpe": "",
                    "script": {"banner": "altered_SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5"},
                },
            }
        },
    }
    store_results("127.0.0.1", results)
    assert EndpointGenericScan.objects.all().count() == 23


def test_re_evaluate_bannergrab_versions(db):

    url = Url.objects.create(url="basisbeveiliging.nl")
    UrlIp.objects.create(url=url, ip="127.0.0.1", is_v4=True, discovered_on=datetime.now(pytz.utc))

    # This should change exactly nothing.
    assert re_evaluate_bannergrab_versions() == 0

    # Add an empty result, then upgrade it
    results = {
        **generic_data,
        **{
            "tcp": {
                22: {
                    "state": "open",
                    "reason": "syn-ack",
                    "name": "ssh",
                    "product": "",
                    "version": "",
                    "extrainfo": "",
                    "conf": "10",
                    "cpe": "",
                    "script": {"banner": "apache"},
                },
            }
        },
    }
    store_results("127.0.0.1", results)

    assert EndpointGenericScan.objects.count() == 1

    # Now make sure it _does_ change something
    epgs = EndpointGenericScan.objects.all().filter(rating="service_identity_some_identity_found").first()
    epgs.evidence = "SSH-2.0-OpenSSH_8.2p1 Ubuntu-4ubuntu0.5"
    epgs.save()
    assert re_evaluate_bannergrab_versions() == 1

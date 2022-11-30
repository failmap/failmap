from websecmap.organizations.models import Url
from websecmap.scanners.scanner.subdomains import dnsrecon_parse_report_contents


def test_dnsrecon_parse_report_contents(db, mocker):
    mocker.patch("websecmap.scanners.scanner.http.resolves", return_value=True)

    url = Url.objects.create(url="basisbeveiliging.nl")

    contents = [
        {"type": "A", "name": "basisbeveiliging.nl", "address": "1.1.1.1"},
        {"type": "AAAA", "name": "basisbeveiliging.nl", "address": "2a00:d00:ff:...."},
        {"type": "A", "name": "something.somthing.something.darkside.example.com", "address": "no_ip"},
        {"type": "CNAME", "name": "something.basisbeveiliging.nl", "address": "1.1.1.1"},
        {"type": "A", "name": "*.basisbeveiliging.nl", "address": "1.1.1.1"},
    ]

    dnsrecon_parse_report_contents(contents, url.as_dict())

    # something.basisbeveilging.nl has been added
    assert Url.objects.all().count() == 2

    # test that results with a canary are never added
    contents = [
        {"type": "A", "name": "basisbeveiliging.nl", "address": "1.1.1.1"},
        {"type": "A", "name": "something_else.basisbeveiliging.nl", "address": "1.1.1.1"},
        {"type": "A", "name": "another.basisbeveiliging.nl", "address": "1.1.1.1"},
        {"type": "A", "name": "does_not_exist_canary.basisbeveiliging.nl", "address": "1.1.1.1"},
    ]

    dnsrecon_parse_report_contents(contents, url.as_dict())
    assert Url.objects.all().count() == 2

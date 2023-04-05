from django.forms import model_to_dict

import websecmap
from websecmap.organizations.models import UrlWhois, Url
from websecmap.organizations.whois.sidn import parse_whois_data, update_whois_data
from websecmap.scanners.models import ScanProxy

responses = {
    # normal responses
    "sidn.nl": """{"type":"WHO_IS","status":{"code":200,"message":"OK"},"errors":[],"warnings":[{"type":"CLEANUP_DETECT_URL"}],"changed":false,"details":{"domain":"sidn.nl","state":{"type":"ACTIVE"},"registrar":"Stichting Internet Domeinregistratie Nederland\nMeander 501\n6825MD Arnhem\nNetherlands","abuse":"+31.263525555\nabuse@sidn.nl","dnsSec":true,"nameServers":[{"hostname":"ns4.sidn.nl","ip-address":"212.114.120.108"},{"hostname":"ns4.sidn.nl","ip-address":"2001:7b8:62b:1:0:d4ff:fe72:786c"},{"hostname":"ns5.sidn.nl","ip-address":"2604:1380:4601:6300::1"},{"hostname":"ns5.sidn.nl","ip-address":"145.40.68.55"},{"hostname":"ns3.sidn.nl","ip-address":"2001:678:34:0:194:0:30:2"},{"hostname":"ns3.sidn.nl","ip-address":"194.0.30.2"}],"creationDate":"1999-11-18","updatedDate":"2021-10-14","maintainer":"NL Domain Registry","registrant":"Stichting Internet Domeinregistratie Nederland","adminContact":"support@sidn.nl","techContacts":["support@sidn.nl"],"optOut":false,"domicile":false,"copyright":"Copyright notice No part of this publication may be reproduced, published, stored in a retrieval system, or transmitted, in any form or by any means, electronic, mechanical, recording, or otherwise, without prior permission of the Foundation for Internet Domain Registration in the Netherlands (SIDN). These restrictions apply equally to registrars, except in that reproductions and publications are permitted insofar as they are reasonable, necessary and solely in the context of the registration activities referred to in the General Terms and Conditions for .nl Registrars. Any use of this material for advertising, targeting commercial offers or similar activities is explicitly forbidden and liable to result in legal action. Anyone who is aware or suspects that such activities are taking place is asked to inform the Foundation for Internet Domain Registration in the Netherlands. ©The Foundation for Internet Domain Registration in the Netherlands (SIDN) Dutch Copyright Act, protection of authors' rights (Section 10, subsection 1, clause 1)."},"_links":{"self":{"href":"https://api.sidn.nl/rest/whois?domain=sidn.nl"}}}""",  # noqa
    "basisbeveiliging.nl": """{"type":"WHO_IS","status":{"code":200,"message":"OK"},"errors":[],"warnings":[{"type":"CLEANUP_DETECT_URL"}],"changed":false,"details":{"domain":"sidn.nl","state":{"type":"ACTIVE"},"registrar":"Stichting Internet Domeinregistratie Nederland\nMeander 501\n6825MD Arnhem\nNetherlands","abuse":"+31.263525555\nabuse@sidn.nl","dnsSec":true,"nameServers":[{"hostname":"ns4.sidn.nl","ip-address":"212.114.120.108"},{"hostname":"ns4.sidn.nl","ip-address":"2001:7b8:62b:1:0:d4ff:fe72:786c"},{"hostname":"ns5.sidn.nl","ip-address":"2604:1380:4601:6300::1"},{"hostname":"ns5.sidn.nl","ip-address":"145.40.68.55"},{"hostname":"ns3.sidn.nl","ip-address":"2001:678:34:0:194:0:30:2"},{"hostname":"ns3.sidn.nl","ip-address":"194.0.30.2"}],"creationDate":"1999-11-18","updatedDate":"2021-10-14","maintainer":"NL Domain Registry","registrant":"Stichting Internet Domeinregistratie Nederland","adminContact":"support@sidn.nl","techContacts":["support@sidn.nl"],"optOut":false,"domicile":false,"copyright":"Copyright notice No part of this publication may be reproduced, published, stored in a retrieval system, or transmitted, in any form or by any means, electronic, mechanical, recording, or otherwise, without prior permission of the Foundation for Internet Domain Registration in the Netherlands (SIDN). These restrictions apply equally to registrars, except in that reproductions and publications are permitted insofar as they are reasonable, necessary and solely in the context of the registration activities referred to in the General Terms and Conditions for .nl Registrars. Any use of this material for advertising, targeting commercial offers or similar activities is explicitly forbidden and liable to result in legal action. Anyone who is aware or suspects that such activities are taking place is asked to inform the Foundation for Internet Domain Registration in the Netherlands. ©The Foundation for Internet Domain Registration in the Netherlands (SIDN) Dutch Copyright Act, protection of authors' rights (Section 10, subsection 1, clause 1)."},"_links":{"self":{"href":"https://api.sidn.nl/rest/whois?domain=sidn.nl"}}}""",  # noqa
    # odd cases
    "nodate.nl": """{"type":"WHO_IS","status":{"code":200,"message":"OK"},"errors":[],"warnings":[{"type":"CLEANUP_DETECT_URL"},{"type":"CLEANUP_DOT_NL_ONLY"}],"changed":true,"details":{"domain":"","state":{"type":"FREE"},"registrar":"","dnsSec":false,"maintainer":"","optOut":false,"domicile":false,"copyright":"Copyright notice No part of this publication may be reproduced, published, stored in a retrieval system, or transmitted, in any form or by any means, electronic, mechanical, recording, or otherwise, without prior permission of the Foundation for Internet Domain Registration in the Netherlands (SIDN). These restrictions apply equally to registrars, except in that reproductions and publications are permitted insofar as they are reasonable, necessary and solely in the context of the registration activities referred to in the General Terms and Conditions for .nl Registrars. Any use of this material for advertising, targeting commercial offers or similar activities is explicitly forbidden and liable to result in legal action. Anyone who is aware or suspects that such activities are taking place is asked to inform the Foundation for Internet Domain Registration in the Netherlands. ©The Foundation for Internet Domain Registration in the Netherlands (SIDN) Dutch Copyright Act, protection of authors' rights (Section 10, subsection 1, clause 1)."},"_links":{"self":{"href":"https://api.sidn.nl/rest/whois?domain=mecklenburg-vorpommern.nl"}}}""",  # noqa
    "toofast.nl": """{"code":429,"error":"Too many requests","id":"1fG5msV_Q2SZ_rjsgVQsBA"}""",
}


def patched_get_whois_data(url, proxy_protocol: str = None, proxy_address: str = None):
    return responses.get(url)


def test_parse_whois_data():
    whois: UrlWhois = parse_whois_data(responses["sidn.nl"])
    output = model_to_dict(whois)
    # make test case shorter:
    output["whois_record_data"] = ""
    # remove sequential id's due to other testcases
    output["url"] = 1

    assert output == {
        "abuse": "+31.263525555\n" "abuse@sidn.nl",
        "admin_contact": "support@sidn.nl",
        "creation_date": "1999-11-18",
        "id": None,
        "is_the_latest": True,
        "registrant": "Stichting Internet Domeinregistratie Nederland",
        "reseller": "",
        "updated_date": "2021-10-14",
        "url": 1,
        "whois_record_data": "",
        "whois_record_type": "json",
    }


def test_update_whois_data(db, monkeypatch):
    ScanProxy.objects.all().delete()

    monkeypatch.setattr(websecmap.organizations.whois.sidn, "get_whois_data", patched_get_whois_data)

    url, _ = Url.objects.get_or_create(url="sidn.nl")
    url, _ = Url.objects.get_or_create(url="basisbeveiliging.nl")
    update_whois_data(**{"rate_limit_in_seconds": 0})
    assert UrlWhois.objects.count() == 2


def test_deduplication(db, monkeypatch):
    ScanProxy.objects.all().delete()

    monkeypatch.setattr(websecmap.organizations.whois.sidn, "get_whois_data", patched_get_whois_data)
    url, _ = Url.objects.get_or_create(url="sidn.nl")

    # should not cause duplicates or extra objects given the date is the same
    update_whois_data(**{"rate_limit_in_seconds": 0})
    update_whois_data(**{"rate_limit_in_seconds": 0})
    update_whois_data(**{"rate_limit_in_seconds": 0})
    update_whois_data(**{"rate_limit_in_seconds": 0})
    update_whois_data(**{"rate_limit_in_seconds": 0})
    update_whois_data(**{"rate_limit_in_seconds": 0})
    assert UrlWhois.objects.count() == 1

    # change the date of the current record to simulate that new data is being retrieved:
    UrlWhois.objects.update(updated_date="2020-01-01")
    update_whois_data(**{"rate_limit_in_seconds": 0})
    assert UrlWhois.objects.count() == 2
    assert UrlWhois.objects.filter(is_the_latest=True).count() == 1
    assert UrlWhois.objects.filter(is_the_latest=False).count() == 1


def test_update_whois_data_no_date(db, monkeypatch):
    ScanProxy.objects.all().delete()

    # alternative cases with more annoying results
    monkeypatch.setattr(websecmap.organizations.whois.sidn, "get_whois_data", patched_get_whois_data)

    # some results do not have an update date at all...
    url, _ = Url.objects.get_or_create(url="nodate.nl")
    update_whois_data(**{"rate_limit_in_seconds": 0})
    assert UrlWhois.objects.count() == 1
    assert UrlWhois.objects.all().first().updated_date is None

    # When receiving no date as above, it should not save twice for now:
    update_whois_data(**{"rate_limit_in_seconds": 0})
    update_whois_data(**{"rate_limit_in_seconds": 0})
    assert UrlWhois.objects.count() == 1


def test_update_whois_data_too_fast(db, monkeypatch):
    ScanProxy.objects.all().delete()

    # alternative cases with more annoying results
    monkeypatch.setattr(websecmap.organizations.whois.sidn, "get_whois_data", patched_get_whois_data)

    # some results do not have an update date at all...
    # should not crash, but does affect the rate limit
    url, _ = Url.objects.get_or_create(url="toofast.nl")
    update_whois_data(**{"rate_limit_in_seconds": 0})
    assert UrlWhois.objects.count() == 0

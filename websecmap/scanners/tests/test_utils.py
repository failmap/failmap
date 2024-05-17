from datetime import datetime, timezone

from constance.test import override_config

from websecmap.scanners.models import EndpointGenericScan
from websecmap.scanners.scanner.utils import get_nameservers

import json


@override_config(SCANNER_NAMESERVERS=["2.2.2.2", "3.3.3.3"])
def test_get_nameservers_with_custom_config(db):
    # Name of this test is intended to go after test_get_nameservers due to cache being overridden.
    servers = get_nameservers()
    assert len(servers) == 2
    assert servers == ["2.2.2.2", "3.3.3.3"]


def test_meaning(db):
    # This is written because meaning was stored with single qoutes in the jsonfield. But we need to
    # export it as valid json in reports: single qouted json is not valid and impossible to parse in complex
    # scenarios. Those complex scenarios have also been added. Here you can see how thigns work.
    # note that by design integer keys are converted to strings!

    some_data = {"test": 1, "1": 2, "string's1": "'\"'''", 'string"s2': '"""\''}

    epgs = EndpointGenericScan()
    epgs.meaning = some_data
    epgs.rating_determined_on = datetime.now(timezone.utc)
    epgs.save()

    # log.warning(epgs.__class__)
    # log.warning(some_data.__class__)

    data = EndpointGenericScan.objects.get(pk=epgs.pk)
    assert data.meaning == some_data

    # log.warning(data.meaning.__class__)
    # assert 1 == 2
    dumps_meaning = json.dumps(data.meaning)

    # has to have double qoutes.
    assert dumps_meaning == '{"test": 1, "1": 2, "string\'s1": "\'\\"\'\'\'", "string\\"s2": "\\"\\"\\"\'"}'

    # now work with the raw value and try to casts that to the real one...

    """
    Note that when exporting and importing via DjangoImportExportAdmin json will be converted to string
    and not converted back! You will have to do that manually.

    For example like this:

    from websecmap.scanners.models import EndpointGenericScan
    scans = EndpointGenericScan.objects.filter(id__gte=29579591)
    for scan in scans:
        try:
            meaning = json.loads(scan.meaning.replace("'", '"').replace("None", "null"))
            scan.meaning = meaning
            scan.save()
        except Exception:
            print(f"could not convert {scan.id}")
    """

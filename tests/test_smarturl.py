from failmap_admin.organizations.dashboard_modules import SmartAddUrl
from failmap_admin.organizations.models import Organization, Url


def test_adding_urls(db):
    """When given a bunch of URLs all valid ones should be added."""

    urls = """a
a.a
a.a.a
arnhem.nl
www.arnhem.nl
https://arnhem.nl
https://nieuwdomein.arnhem.nl
https://dubbelnieuw.arnhem.nl
https://dubbelnieuw.arnhem.nl
https://user:password@userpassdomain.arnhem.nl
https://querydomein.arnhem.nl/hello/?input=1#selector
https://arnhem.blaat.nl
https://#$%^&*(.arnhem.nl
http://nonexistingdomain.nl
<tagsubdomain>.arnhem.nl"""

    o = Organization(name="Arnhem", country="Netherlands")
    o.save()
    Url(organization=o, url="arnhem.nl").save()

    smartaddurl = SmartAddUrl()
    smartaddurl.add(urls)

    # for debugging failed test
    print([(r.domain, r.error, r.message) for r in smartaddurl.addresult])

    # these urls should have been added
    assert Url.objects.filter(url='arnhem.nl')
    assert Url.objects.filter(url='nieuwdomein.arnhem.nl')
    assert Url.objects.filter(url='dubbelnieuw.arnhem.nl')
    assert Url.objects.filter(url='dubbelnieuw.arnhem.nl')

    # invalid entries
    assert not Url.objects.filter(url='a.a')

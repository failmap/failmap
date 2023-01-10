from websecmap.organizations.models import Url
from websecmap.organizations.nuke import nuke_url


def test_nuke_url(db):
    Url.objects.create(url="test.nl")
    Url.objects.create(url="www.arnhem.nl")
    Url.objects.create(url="test.zutphen.nl")
    Url.objects.create(url="test2.zutphen.nl")

    assert Url.objects.all().count() == 4

    # removing regular test
    nuke_url(domain="test")
    assert Url.objects.all().count() == 3

    # only deleting test, not test2
    nuke_url(domain="zutphen", excluded_subdomains=["test"])
    assert Url.objects.all().count() == 2

    # wrong suffix, not deleted
    nuke_url(domain="arnhem", suffix="nu")
    assert Url.objects.all().count() == 2

    nuke_url(domain="arnhem", excluded_subdomains=["www"])
    assert Url.objects.all().count() == 2

    nuke_url(domain="arnhem")
    assert Url.objects.all().count() == 1

    # nuke multiple at the same time
    Url.objects.create(url="test.basisbeveiliging.nl")
    Url.objects.create(url="test2.basisbeveiliging.nl")
    Url.objects.create(url="test3.basisbeveiliging.nl")
    assert Url.objects.all().count() == 4

    nuke_url(domain="basisbeveiliging")
    assert Url.objects.all().count() == 1

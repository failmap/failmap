from websecmap.organizations.models import Url
from websecmap.pro.models import Account, UrlList
from websecmap.scanners.models import Endpoint, EndpointGenericScan


def test_explanations(db):

    # create account, url, urllist, endpoint and scan. Perform stuff on scan.

    # todo: add credits to account.
    # todo: write tests for credit mutations.
    account, created = Account.objects.all().get_or_create(name="test")
    account.receive_credits(100, 'Test Explanation')

    url, created = Url.objects.all().get_or_create(url='websecuritymap.org', is_dead=False, not_resolvable=False)

    urllist, created = UrlList.objects.all().get_or_create(name='test', account=account)

    urllist.urls.add(url)
    urllist.save()

    endpoint, created = Endpoint.objects.all().get_or_create(
        url=url, protocol='https', port='443', ip_version=4, is_dead=False)

    perfect_scan, created = EndpointGenericScan.objects.all().get_or_create(
        endpoint=endpoint, type='tls_qualys_encryption_quality', rating='F', is_the_latest_scan=True)

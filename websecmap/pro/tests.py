import random

from websecmap.organizations.models import Url
from websecmap.pro.logic.comply_or_explain import (explain_costs, get_canned_explanations,
                                                   try_explain)
from websecmap.pro.models import Account, UrlList
from websecmap.scanners.models import Endpoint, EndpointGenericScan


def test_explanations(db):

    # create account, url, urllist, endpoint and scan. Perform stuff on scan.

    # todo: add credits to account.
    # todo: write tests for credit mutations.
    account, created = Account.objects.all().get_or_create(name="test")

    url, created = Url.objects.all().get_or_create(url='websecuritymap.org', is_dead=False, not_resolvable=False)

    urllist, created = UrlList.objects.all().get_or_create(name='test', account=account)

    urllist.urls.add(url)
    urllist.save()

    endpoint, created = Endpoint.objects.all().get_or_create(
        url=url, protocol='https', port='443', ip_version=4, is_dead=False)

    scan, created = EndpointGenericScan.objects.all().get_or_create(
        endpoint=endpoint, type='tls_qualys_encryption_quality', rating='F', is_the_latest_scan=True)

    scan2, created = EndpointGenericScan.objects.all().get_or_create(
        endpoint=endpoint, type='some_type', rating='F', is_the_latest_scan=True)

    canned_explanation = random.choice(get_canned_explanations())
    assert len(canned_explanation) > 10

    # Make sure an explanation can happen
    account.receive_credits(explain_costs(), 'Test Explanation')
    explained = try_explain(account=account, scan_id=scan.pk, scan_type=scan.type, explanation=canned_explanation)
    assert explained['success'] is True and explained['message'] == "Explanation saved."

    # not enough credits
    explained = try_explain(account=account, scan_id=scan2.pk, scan_type=scan2.type, explanation=canned_explanation)
    assert explained['success'] is False and explained['message'] == "This account does not have enough credits to " \
                                                                     "perform this operation. Please contact " \
                                                                     "support to upgrade your account."

    # incorrect scan
    account.receive_credits(explain_costs(), 'Test Explanation')
    explained = try_explain(account=account, scan_id=-10, scan_type=scan.type, explanation=canned_explanation)
    assert explained['success'] is False and explained['message'] == "This is not a valid scan."

    # existing explanation can be altered free of charge:
    explained = try_explain(account=account, scan_id=scan.pk, scan_type=scan.type, explanation="changed!")
    assert explained['success'] is True and explained['message'] == "Explanation altered."

    # empty explanation, and we still have the credits from the previous incorrect scan
    explained = try_explain(account=account, scan_id=scan2.pk, scan_type=scan2.type, explanation=canned_explanation)
    assert explained['success'] is True and explained['message'] == "Explanation saved."

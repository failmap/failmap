import random

import pytest
from django.utils import timezone

from websecmap.organizations.models import Url
from websecmap.pro.logic.comply_or_explain import (explain_costs, extend_explanation,
                                                   get_canned_explanations, get_scan,
                                                   remove_explanation, try_explain)
from websecmap.pro.models import Account, CreditMutation, UrlList
from websecmap.scanners.models import Endpoint, EndpointGenericScan


def test_credits(db):
    account, created = Account.objects.all().get_or_create(name="test")

    account.receive_credits(100, "test")

    assert account.can_spend(100) is True
    assert account.can_spend(101) is False

    account.spend_credits(100, "test")
    assert account.credits == 0

    # two transactions
    assert CreditMutation.objects.all().filter(account=account).count() == 2

    with pytest.raises(ValueError, match=r'.*balance.*'):
        account.spend_credits(100, "test")

    # failure does not create a transaction
    assert CreditMutation.objects.all().filter(account=account).count() == 2

    # todo: should we assert a message is added?


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
        endpoint=endpoint, type='tls_qualys_encryption_quality', rating='F', is_the_latest_scan=True,
        rating_determined_on=timezone.now())

    scan2, created = EndpointGenericScan.objects.all().get_or_create(endpoint=endpoint, type='plain_https', rating='F',
                                                                     is_the_latest_scan=True,
                                                                     rating_determined_on=timezone.now())

    # see if we can get the same scan back:
    retrieved_scan = get_scan(account, scan.id, scan.type)
    assert scan == retrieved_scan

    retrieved_scan = get_scan(account, scan2.id, scan2.type)
    assert scan2 == retrieved_scan

    # an account cannot get any scan information about scans in lists of others etc...
    fake_account, created = Account.objects.all().get_or_create(name="fake")
    retrieved_scan = get_scan(fake_account, scan.id, scan.type)
    assert None is retrieved_scan

    retrieved_scan = get_scan(fake_account, scan2.id, scan2.type)
    assert None is retrieved_scan

    # Make sure there are canned explanations.
    assert len(get_canned_explanations()) > 2

    canned_explanation = random.choice(get_canned_explanations())
    assert len(canned_explanation) > 10

    # Make sure an explanation can happen
    account.receive_credits(explain_costs(), 'Test Explanation')
    explained = try_explain(account=account, scan_id=scan.pk, scan_type=scan.type, explanation=canned_explanation)
    assert explained['message'] == "Explanation saved." and explained['success'] is True

    # not enough credits to explain another scan.
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

    # another explanation, and we still have the credits from the previous incorrect scan
    explained = try_explain(account=account, scan_id=scan2.pk, scan_type=scan2.type, explanation=canned_explanation)
    assert explained['success'] is True and explained['message'] == "Explanation saved."

    # explanation can be removed
    removed = remove_explanation(account=account, scan_id=scan2.pk, scan_type=scan2.type)
    assert removed['success'] is True and removed['message'] == "Explanation removed."

    # invalid scan
    empty_account, created = Account.objects.all().get_or_create(name="test2")
    removed = remove_explanation(account=empty_account, scan_id=scan2.pk, scan_type=scan2.type)
    assert removed['success'] is False and removed['message'] == "This is not a valid scan."

    removed = remove_explanation(account=empty_account, scan_id=-10, scan_type=scan2.type)
    assert removed['success'] is False and removed['message'] == "This is not a valid scan."

    removed = remove_explanation(account=empty_account, scan_id=-scan2.pk, scan_type='yolo')
    assert removed['success'] is False and removed['message'] == "This is not a valid scan."

    # extending:
    # not enough credits
    explained = extend_explanation(account=account, scan_id=scan.pk, scan_type=scan.type)
    assert explained['success'] is False and explained['message'] == "This account does not have enough credits to " \
                                                                     "perform this operation. Please contact " \
                                                                     "support to upgrade your account."

    account.receive_credits(explain_costs(), 'Test Explanation')
    explained = extend_explanation(account=account, scan_id=scan.pk, scan_type=scan.type)
    assert explained['success'] is True and explained['message'] == "Explanation extended."

    # todo: parameterize test cases for permission checks on each of these methods.

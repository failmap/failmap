from datetime import timedelta
from typing import Any, Dict, Union

from django.utils import timezone

from websecmap.pro.models import Account
from websecmap.reporting.severity import get_severity
from websecmap.scanners import ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan

# todo: make it impossible to explain past scans. Only allow explanations on "is_the_latest_scan" otherwise it
# may be unnecessarily costly and complex to manage.
# Done: prevent explanations costing something when it's already explained.


def explain_costs():
    return 100


def get_canned_explanations():

    return [
        "The certificate is used on specific devices exclusively, they trust the certificate.",
        "It is not possible to set up these headers, as the server software doesn't allow this.",
        "The issue is being fixed by the supplier, a new version will be delivered soon.",
    ]


def try_explain(account: Account, scan_id: int, scan_type: str, explanation: str) -> Dict[str, Any]:

    scan = get_scan(account, scan_id, scan_type)
    if not scan:
        return {'error': True, 'success': False, 'message': 'This is not a valid scan.'}

    if not explanation:
        return {'error': True, 'success': False, 'message': 'Explanation was empty, could not save explanation.'}

    # you can change the explanation at zero cost. It won't extend the expiration date, etc.
    if scan.comply_or_explain_is_explained is True:
        scan.comply_or_explain_explanation = explanation
        scan.save()
        return {'error': False, 'success': True, 'message': 'Explanation altered.'}

    # First explanation costs credits
    if not account.can_spend(explain_costs()):
        return {'error': True, 'success': False,
                'message': 'This account does not have enough credits to perform this operation. Please contact '
                           'support to upgrade your account.'}

    scan.comply_or_explain_is_explained = True
    scan.comply_or_explain_explained_by = account.name
    scan.comply_or_explain_explained_on = timezone.now()
    scan.comply_or_explain_explanation_valid_until = timezone.now() + timedelta(days=366)
    scan.comply_or_explain_explanation = explanation
    scan.comply_or_explain_case_handled_by = 'Pro Interface'
    scan.save()

    account.spend_credits(explain_costs(), 'Explanation of scan %s, of type %s.' % (scan_id, scan_type))

    return {'error': False, 'success': True, 'message': 'Explanation saved.'}


def remove_explanation(account: Account, scan_id: int, scan_type: str) -> Dict[str, Any]:
    # this is free

    scan = get_scan(account, scan_id, scan_type)
    if not scan:
        return {'success': False, 'error': True, 'message': 'This is not a valid scan.'}

    scan.comply_or_explain_is_explained = False
    scan.save(update_fields=['comply_or_explain_is_explained'])
    return {'success': True, 'error': False, 'message': 'Explanation removed.'}


def extend_explanation(account: Account, scan_id: int, scan_type: str) -> Dict[str, Any]:
    """
    Will extend the validity of the explanation (default a year), for an amount of credits. The maximum is one year.
    This does not stack, so you cannot explain it for dozens of years as that removes the incentive to comply.

    :param scan_id:
    :param scan_type:
    :return:
    """

    if not account.can_spend(explain_costs()):
        return {'error': True, 'success': False,
                'message': 'This account does not have enough credits to perform this operation. Please contact '
                           'support to upgrade your account.'}

    scan = get_scan(account, scan_id, scan_type)
    if not scan:
        return {'error': True, 'success': False, 'message': 'This is not a valid scan.'}

    scan.comply_or_explain_explanation_valid_until = timezone.now() + timedelta(days=366)
    scan.save(update_fields=['comply_or_explain_explanation_valid_until'])
    account.spend_credits(explain_costs(), 'Explanation of scan %s, of type %s.' % (scan_id, scan_type))

    return {'success': True, 'error': False, 'message': 'Explanation extended.'}


def get_scan(account: Account, scan_id: int, scan_type: str) -> Union[EndpointGenericScan, UrlGenericScan, None]:

    if scan_type in ENDPOINT_SCAN_TYPES:
        return EndpointGenericScan.objects.all().filter(
            pk=scan_id, type=scan_type, endpoint__url__urllist__account=account).first()

    if scan_type in URL_SCAN_TYPES:
        return UrlGenericScan.objects.all().filter(
            pk=scan_id, type=scan_type, url__urllist__account=account).first()

    return None


def get_scan_data(account: Account, scan_id: int, scan_type: str):
    scan = get_scan(account, scan_id, scan_type)

    severity = get_severity(scan)

    impact = "high" if severity.get("high", 0) else "medium" if severity.get("medium", 0) else "low" \
        if severity.get("low", 0) else "ok"

    # also get the severity(or is that stored?)
    return {'id': scan.id,
            'rating': scan.rating,
            'explanation': scan.explanation,
            'evidence': scan.evidence,
            'last_scan_moment': scan.last_scan_moment.isoformat(),
            'rating_determined_on': scan.rating_determined_on.isoformat(),
            'is_the_latest_scan': scan.is_the_latest_scan,
            'comply_or_explain_is_explained': scan.comply_or_explain_is_explained,
            'comply_or_explain_explanation_valid_until': scan.comply_or_explain_explanation_valid_until.isoformat(),
            'comply_or_explain_explanation': scan.comply_or_explain_explanation,
            'comply_or_explain_explained_by': scan.comply_or_explain_explained_by,
            'comply_or_explain_explained_on': scan.comply_or_explain_explained_on.isoformat(),
            'comply_or_explain_case_handled_by': scan.comply_or_explain_case_handled_by,
            'comply_or_explain_case_additional_notes': scan.comply_or_explain_case_additional_notes,
            'impact': impact,
            }

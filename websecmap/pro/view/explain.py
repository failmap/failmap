
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from websecmap.app.common import JSEncoder
from websecmap.pro.logic import LOGIN_URL
from websecmap.pro.logic.comply_or_explain import (explain_costs, extend_explanation,
                                                   get_canned_explanations, get_scan_data,
                                                   remove_explanation, try_explain)
from websecmap.pro.logic.shared import get_account


@login_required(login_url=LOGIN_URL)
def get_canned_explanations_view(request) -> JsonResponse:
    return JsonResponse(get_canned_explanations(), encoder=JSEncoder)


@login_required(login_url=LOGIN_URL)
def get_explain_costs_view(request) -> JsonResponse:
    return JsonResponse(explain_costs(), encoder=JSEncoder)


@login_required(login_url=LOGIN_URL)
def get_scan_data_view(request, scan_id, scan_type):
    account = get_account(request)
    data = get_scan_data(account, scan_id, scan_type)
    return JsonResponse(data, encoder=JSEncoder)


@login_required(login_url=LOGIN_URL)
def try_explain_view(request, scan_id, scan_type, explanation):
    account = get_account(request)
    data = try_explain(account, scan_id, scan_type, explanation)
    return JsonResponse(data, encoder=JSEncoder)


@login_required(login_url=LOGIN_URL)
def extend_explanation_view(request, scan_id, scan_type):
    account = get_account(request)
    data = extend_explanation(account, scan_id, scan_type)
    return JsonResponse(data, encoder=JSEncoder)


@login_required(login_url=LOGIN_URL)
def remove_explanation_view(request, scan_id, scan_type):
    account = get_account(request)
    data = remove_explanation(account, scan_id, scan_type)
    return JsonResponse(data, encoder=JSEncoder)

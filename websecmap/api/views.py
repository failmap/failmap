import logging

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render

from websecmap.api.logic import (get_2ndlevel_domains, get_map_configuration, get_uploads,
                                 sidn_domain_upload)

log = logging.getLogger(__package__)

SIDN_LOGIN_URL = '/api/login/?next=/SIDN/'


# todo: verify if the correct account is used (contains "SIDN" in the description)
# todo: user passes test, is SIDN user.


def has_SIDN_permissions(user):
    # Yes, this is an anti pattern. As there was no real need to do a lot with permissions, we start with this
    # as it is _not_ a pattern yet.

    if not user:
        return False

    if not user.is_active:
        return False

    if user.groups.filter(name="SIDN").exists():
        return True

    # superusers and staff always have permission
    if user.is_superuser:
        return True

    if user.is_staff:
        return True

    return False


@login_required(login_url=SIDN_LOGIN_URL)
def show_apis_(request):
    return render(request, 'api/apis.html', {})


@user_passes_test(has_SIDN_permissions, login_url=SIDN_LOGIN_URL)
def sidn_get_map_configuration_(request):
    return JsonResponse(get_map_configuration(), safe=False)


@user_passes_test(has_SIDN_permissions, login_url=SIDN_LOGIN_URL)
def sidn_get_2ndlevel_domains_(request, country, organization_type):
    domains = get_2ndlevel_domains(country, organization_type)
    return JsonResponse(domains, safe=False)


@user_passes_test(has_SIDN_permissions, login_url=SIDN_LOGIN_URL)
def sidn_show_instructions_(request):
    return render(request, 'api/SIDN.html', {})


@user_passes_test(has_SIDN_permissions, login_url=SIDN_LOGIN_URL)
def sidn_domain_upload_(request):
    data = request.POST.get('data', "")
    if not data:
        return JsonResponse({'result': 'no data supplied, not going to process request'})
    sidn_domain_upload.apply_async([request.user, data])
    return JsonResponse({'result': 'processing'})


@user_passes_test(has_SIDN_permissions, login_url=SIDN_LOGIN_URL)
def sidn_get_uploads_(request):
    return JsonResponse(get_uploads(request.user), safe=False, json_dumps_params={
        'sort_keys': False, 'indent': 4, 'separators': (',', ': ')
    })

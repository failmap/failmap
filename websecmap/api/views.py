import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from websecmap.api.logic import get_2ndlevel_domains, get_map_configuration, sidn_domain_upload

log = logging.getLogger(__package__)

SIDN_LOGIN_URL = '/api/login/?next=/SIDN/'

# todo: get data from request
# todo: verify if the correct account is used (contains "SIDN" in the description)
# todo: user passes test, is SIDN user.


@login_required(login_url=SIDN_LOGIN_URL)
def get_map_configuration_(request):
    return JsonResponse(get_map_configuration(), safe=False)


@login_required(login_url=SIDN_LOGIN_URL)
def get_2ndlevel_domains_(request, country, organization_type):
    domains = get_2ndlevel_domains(country, organization_type)
    return JsonResponse(domains, safe=False)


@login_required(login_url=SIDN_LOGIN_URL)
def show_sidn_upload_(request):
    return render(request, 'api/SIDN.html', {})


@login_required(login_url=SIDN_LOGIN_URL)
def sidn_domain_upload_(request):
    data = request.POST.get('data', "")
    added = sidn_domain_upload(data)
    return JsonResponse({'number_of_added_domains': len(added)})

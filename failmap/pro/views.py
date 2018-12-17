import logging

from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.http import JsonResponse
from django.shortcuts import render

from failmap.app.common import JSEncoder
from failmap.map.calculate import get_calculation
from failmap.pro.models import ProUser, UrlList
from failmap.scanners.models import EndpointGenericScan, UrlGenericScan
from failmap.scanners.types import ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES

log = logging.getLogger(__package__)


# Create your views here.
@login_required(login_url='/pro/login/?next=/pro/')
def dummy(request):
    return JsonResponse({'hello': 'world'}, encoder=JSEncoder)


def home(request):
    return render(request, 'pro/home.html', {})


def scans(request):

    all_scans = []

    scans = list(EndpointGenericScan.objects.filter(
        endpoint__url__urllist__account=1,
        type__in=ENDPOINT_SCAN_TYPES
    ).order_by('-rating_determined_on')[0:600])

    scans += list(UrlGenericScan.objects.filter(
        url__urllist__account=1,
        type__in=URL_SCAN_TYPES
    ).order_by('-rating_determined_on')[0:6])

    for scan in scans:
        calculation = get_calculation(scan)

        if scan.type in URL_SCAN_TYPES:
            # url scans
            all_scans.append({
                "url": scan.url.url,
                "service": "%s" % scan.url.url,
                "protocol": scan.type,
                "type": scan.type,
                "port": "-",
                "ip_version": "-",
                "explanation": calculation.get("explanation", ""),
                "high": calculation.get("high", 0),
                "medium": calculation.get("medium", 0),
                "low": calculation.get("low", 0),
                "last_scan_humanized": naturaltime(scan.last_scan_moment),
                "last_scan_moment": scan.last_scan_moment.isoformat()
            })
        else:
            # endpoint scans
            all_scans.append({
                "url": scan.endpoint.url.url,
                "service": "%s/%s (IPv%s)" % (scan.endpoint.protocol, scan.endpoint.port, scan.endpoint.ip_version),
                "protocol": scan.endpoint.protocol,
                "port": scan.endpoint.port,
                "type": scan.type,
                "ip_version": scan.endpoint.ip_version,
                "explanation": calculation.get("explanation", ""),
                "high": calculation.get("high", 0),
                "medium": calculation.get("medium", 0),
                "low": calculation.get("low", 0),
                "last_scan_humanized": naturaltime(scan.last_scan_moment),
                "last_scan_moment": scan.last_scan_moment.isoformat()
            })

    return render(request, 'pro/scans.html', {'scans': all_scans})


def urls(request):

    lists = UrlList.objects.all().filter(account=getAccount(request)).prefetch_related('urls')

    return render(request, 'pro/urls.html', {'lists': lists})


def mail(request):
    # mail settings

    return render(request, 'pro/urls.html', {})


def empty_response():
    return JsonResponse({}, encoder=JSEncoder)


def getAccount(request):
    try:
        return ProUser.objects.all().filter(user=request.user).first().account
    except AttributeError:
        raise AttributeError('Logged in user does not have a pro user account associated. Please associate one or login'
                             'as another user.')

import logging
from datetime import datetime

import pytz
from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.http import JsonResponse
from django.shortcuts import render

from failmap.app.common import JSEncoder
from failmap.map.calculate import get_calculation
from failmap.pro.models import CreditMutation, ProUser, RescanRequest, UrlList
from failmap.scanners.models import EndpointGenericScan, UrlGenericScan
from failmap.scanners.types import ALL_SCAN_TYPES, ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES

log = logging.getLogger(__package__)


# Create your views here.
@login_required(login_url='/pro/login/?next=/pro/')
def dummy(request):
    return JsonResponse({'hello': 'world'}, encoder=JSEncoder)


def home(request):
    return render(request, 'pro/home.html', {})


def rescan_costs(scan):
    calculation = get_calculation(scan)

    cost = 100 if calculation.get("high", 0) else 50 if calculation.get("medium", 0) \
        else 20 if calculation.get("low", 0) else 10

    return cost


def scans(request):
    all_scans_view = []

    account = getAccount(request)

    rescan_requests = list(RescanRequest.objects.all().filter(account=account).exclude(status="finished"))
    endpoint_rescanned_ids = [x.scan_id for x in rescan_requests if x.scan_type in ENDPOINT_SCAN_TYPES]
    url_rescanned_ids = [x.scan_id for x in rescan_requests if x.scan_type in URL_SCAN_TYPES]

    latest_scans = list(EndpointGenericScan.objects.filter(
        endpoint__url__urllist__account=account,
        type__in=ENDPOINT_SCAN_TYPES,
        is_the_latest_scan=True
    ).order_by('-rating_determined_on').select_related('endpoint', 'endpoint__url'))

    latest_scans += list(UrlGenericScan.objects.filter(
        url__urllist__account=account,
        type__in=URL_SCAN_TYPES,
        is_the_latest_scan=True
    ).order_by('-rating_determined_on').select_related('url'))

    for scan in latest_scans:
        calculation = get_calculation(scan)

        impact = "high" if calculation.get("high", 0) else "medium" if calculation.get("medium", 0) else "low" \
            if calculation.get("low", 0) else "ok"
        bootstrap_impact = "danger" if calculation.get("high", 0) else "warning" if calculation.get("medium", 0) \
            else "info" if calculation.get("low", 0) else "success"

        sort_impact = 3 if calculation.get("high", 0) else 2 if calculation.get("medium", 0) \
            else 1 if calculation.get("low", 0) else 0

        # todo: this should be standardized somewhere.
        rescan_cost = rescan_costs(scan)

        if scan.type in URL_SCAN_TYPES:
            # url scans
            all_scans_view.append({
                "id": scan.id,
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
                "impact": impact,
                "bootstrap_impact": bootstrap_impact,
                "sort_impact": sort_impact,
                "rescan_cost": rescan_cost,
                "last_scan_humanized": naturaltime(scan.last_scan_moment),
                "last_scan_moment": scan.last_scan_moment.isoformat(),
                "last_scan_moment_python": scan.last_scan_moment,
                "being_rescanned": scan.id in url_rescanned_ids
            })
        else:
            # endpoint scans
            all_scans_view.append({
                "id": scan.id,
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
                "impact": impact,
                "bootstrap_impact": bootstrap_impact,
                "sort_impact": sort_impact,
                "rescan_cost": rescan_cost,
                "last_scan_humanized": naturaltime(scan.last_scan_moment),
                "last_scan_moment": scan.last_scan_moment.isoformat(),
                "last_scan_moment_python": scan.last_scan_moment,
                "being_rescanned": scan.id in endpoint_rescanned_ids
            })

    # sort the scans, so url and endpointscans mingle correctly
    all_scans_view = sorted(all_scans_view, key=lambda k: (k['sort_impact'], k['url'], k['last_scan_moment_python']),
                            reverse=True)

    return render(request, 'pro/scans.html', {'latest_scans': all_scans_view,
                                              'credits': account.credits,
                                              'rescan_requests': rescan_requests})


@login_required(login_url='/pro/login/?next=/pro/')
def account(request):
    this_account = getAccount(request)

    transactions = CreditMutation.objects.all().filter(account=this_account)

    return render(request, 'pro/account.html', {'transactions': transactions,
                                                'credits': this_account.credits})


@login_required(login_url='/pro/login/?next=/pro/')
def urls(request):

    lists = UrlList.objects.all().filter(account=getAccount(request)).prefetch_related('urls')

    return render(request, 'pro/urls.html', {'lists': lists})


@login_required(login_url='/pro/login/?next=/pro/')
def mail(request):
    # mail settings

    return render(request, 'pro/urls.html', {})


# todo: should also be able to rescan directly from e-mail, which should not require a login.
# this should be done with a special code or something that is unique per finding and cannot be guessed :)
# todo: how to prevent re-queue-ing? How to log a scan request / follow a performed scan?
# todo: create a "rescan all" option.
# todo: check if scan already is requested.
@login_required(login_url='/pro/login/?next=/pro/')
def rescan_request(request, scan_type, scan_id):

    account = getAccount(request)

    if scan_type not in ALL_SCAN_TYPES:
        log.debug('No valid scan type.')
        return error_response('Could not create rescan request.')

    if RescanRequest.objects.all().filter(scan_type=scan_type, scan_id=scan_id).exclude(status='finished').exists():
        log.debug('Scan request already exists.')
        return error_response('A scan request for this scan was already made.')

    scan = None
    url = None
    endpoint = None
    if scan_type in ENDPOINT_SCAN_TYPES:
        try:
            scan = EndpointGenericScan.objects.all().filter(
                pk=scan_id,
                is_the_latest_scan=True,
                endpoint__url__urllist__account=account
            ).prefetch_related('endpoint', 'endpoint__url').get()
            endpoint = scan.endpoint
            url = scan.endpoint.url
        except EndpointGenericScan.DoesNotExist:
            log.debug('Not a valid ENDPOINT scan ID, not in this account or not the latest scan.')
            return error_response('Could not create rescan request.')
    else:
        if scan_type in URL_SCAN_TYPES:
            try:
                scan = UrlGenericScan.objects.all().filter(
                    pk=scan_id,
                    is_the_latest_scan=True,
                    url__urllist__account=account
                ).get()
                url = scan.url
            except EndpointGenericScan.DoesNotExist:
                log.debug('Not a valid URL scan ID, not in this account or not the latest scan.')
                return error_response('Could not create rescan request.')

    if not scan or not url:
        log.debug('No scan found on this ID.')
        return error_response('Could not create rescan request.')

    # now what? :)
    # log the rescan somewhere, so it can be followed up.
    # should be picked up in a matter of seconds, as high priority. Will be handled by a separate worker thus splitting
    # the UI from the scanning implementation.
    # placing it in a table also allows more efficient bulk-scanning.

    # todo: cost values
    cost = rescan_costs(scan)

    if not account.can_spend(cost):
        return error_response('Not enough credits.')

    try:
        account.spend_credits(cost, 'Requested re-scan of %s on type %s.' % (url, scan_type))
    except ValueError:
        return error_response('Not enough credits.')

    # do we really want to register it? Yes, for bulk purposes, cost tracing, UI feedback, debugging. So... yes.
    rescan = RescanRequest()
    rescan.account = account
    rescan.scan_type = scan_type
    rescan.scan_id = scan_id

    if scan_type in URL_SCAN_TYPES:
        rescan.url = url
        rescan.url_scan = scan

    if scan_type in ENDPOINT_SCAN_TYPES:
        rescan.endpoint = endpoint
        rescan.url = url
        rescan.endpoint_scan = scan

    rescan.added_on = datetime.now(pytz.utc)
    rescan.cost = cost
    rescan.status = "new"
    rescan.save()

    data = {'success': True,
            'message': 'Rescan added to queue. The scan will be performed with the highest priority.',
            'error': False,
            'cost': cost}

    return JsonResponse(data, encoder=JSEncoder)


def empty_response():
    return JsonResponse({}, encoder=JSEncoder)


def error_response(message):
    return JsonResponse({'error': True, 'message': message, 'success': False, 'cost': 0}, encoder=JSEncoder)


# todo: replace with session variable which is faster(?)
def getAccount(request):
    try:
        return ProUser.objects.all().filter(user=request.user).first().account
    except AttributeError:
        raise AttributeError('Logged in user does not have a pro user account associated. Please associate one or login'
                             'as another user.')

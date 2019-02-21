import logging
from datetime import datetime, timedelta

import pytz
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.text import slugify

from websecmap.app.common import JSEncoder
from websecmap.map.calculate import get_calculation
from websecmap.pro.forms import MailSignupForm
from websecmap.pro.models import (Account, CreditMutation, ProUser, RescanRequest, UrlList,
                                  UrlListReport)
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan
from websecmap.scanners.types import ALL_SCAN_TYPES, ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES

log = logging.getLogger(__package__)


# Create your views here.
@login_required(login_url='/pro/login/?next=/pro/')
def dummy(request):
    return JsonResponse({'hello': 'world'}, encoder=JSEncoder)


@login_required(login_url='/pro/login/?next=/pro/')
def home(request):
    account = getAccount(request)

    user = User.objects.all().filter(pk=request.user.id).first()
    prouser = ProUser.objects.all().filter(user=request.user).first()

    accounts = []
    user_is_staff = False

    # some real hot classic old school programming right here
    if user.is_staff:
        user_is_staff = True
        accounts = list(Account.objects.all().values('id', 'name'))

        # you'll get the first entry in the querydict
        if request.POST.get('change_account', None):
            # don't know how inheritance works with user, i think it's ugly.
            prouser.account = Account.objects.get(id=request.POST.get('change_account'))
            prouser.save()

    return render(request, 'pro/home.html',
                  {
                      'admin': settings.ADMIN,
                      'debug': settings.DEBUG,
                      'account': account,
                      'user_is_staff': user_is_staff,
                      'accounts': accounts,
                      'selected_account': prouser.account.id
                  }
                  )


def signup(request):

    if request.POST:
        form = MailSignupForm(request.POST)

        if form.is_valid():
            form.save()
            return render(request, 'pro/registration/signup_success.html')

    else:
        form = MailSignupForm()

    return render(request, 'pro/registration/signup.html', {'form': form})


def rescan_costs(scan):
    calculation = get_calculation(scan)

    cost = 100 if calculation.get("high", 0) else 50 if calculation.get("medium", 0) \
        else 20 if calculation.get("low", 0) else 10

    return cost


def issues(request, list_name: str = ""):
    all_scans_view = []

    account = getAccount(request)

    rescan_requests = list(RescanRequest.objects.all().filter(account=account).exclude(status="finished"))
    endpoint_rescanned_ids = [x.scan_id for x in rescan_requests if x.scan_type in ENDPOINT_SCAN_TYPES]
    url_rescanned_ids = [x.scan_id for x in rescan_requests if x.scan_type in URL_SCAN_TYPES]

    if list_name:
        latest_endpoint_scans = EndpointGenericScan.objects.all().filter(endpoint__url__urllist__name=list_name)
        latest_url_scans = UrlGenericScan.objects.all().filter(url__urllist__name=list_name)
    else:
        latest_endpoint_scans = EndpointGenericScan.objects.all()
        latest_url_scans = UrlGenericScan.objects.all()

    latest_endpoint_scans = latest_endpoint_scans.filter(
        endpoint__url__urllist__account=account,
        type__in=ENDPOINT_SCAN_TYPES,
        is_the_latest_scan=True
    ).order_by('-rating_determined_on').select_related('endpoint', 'endpoint__url')

    latest_url_scans = latest_url_scans.filter(
        url__urllist__account=account,
        type__in=URL_SCAN_TYPES,
        is_the_latest_scan=True
    ).order_by('-rating_determined_on').select_related('url')

    latest_scans = list(latest_url_scans) + list(latest_endpoint_scans)

    for scan in latest_scans:
        calculation = get_calculation(scan)

        impact = "high" if calculation.get("high", 0) else "medium" if calculation.get("medium", 0) else "low" \
            if calculation.get("low", 0) else "ok"

        # don't show things that are fine.
        if impact == "ok":
            continue

        color = "#ff455833" if calculation.get("high", 0) else "#ff9a4533" if calculation.get("medium", 0) \
            else "#fffc4533" if calculation.get("low", 0) else "#a2f59633"

        sort_impact = 0 if calculation.get("high", 0) else 1 if calculation.get("medium", 0) \
            else 2 if calculation.get("low", 0) else 3

        # todo: this should be standardized somewhere.
        rescan_cost = rescan_costs(scan)

        if scan.type in URL_SCAN_TYPES:
            # url scans
            all_scans_view.append({
                "id": scan.id,
                "url": scan.url.url,
                "service": scan.url.url,
                "domain": scan.url.computed_domain,
                "domain_and_impact": "%s_%s" % (scan.url.computed_domain, impact),
                "protocol": scan.type,
                "type": scan.type,
                "header": "report_header_%s" % scan.type,
                "port": "-",
                "ip_version": "-",
                "explanation": calculation.get("explanation", ""),
                "high": calculation.get("high", 0),
                "medium": calculation.get("medium", 0),
                "low": calculation.get("low", 0),
                "impact": impact,
                "color": color,
                "sort_impact": sort_impact,
                "rescan_cost": rescan_cost,
                "last_scan_humanized": naturaltime(scan.last_scan_moment),
                "last_scan_moment": scan.last_scan_moment.isoformat(),
                "last_scan_moment_python": scan.last_scan_moment,
                "being_rescanned": scan.id in url_rescanned_ids,
            })
        else:
            # endpoint scans
            all_scans_view.append({
                "id": scan.id,
                "url": scan.endpoint.url.url,
                "service": "%s/%s (IPv%s)" % (scan.endpoint.protocol, scan.endpoint.port, scan.endpoint.ip_version),
                "domain": scan.endpoint.url.computed_domain,
                "domain_and_impact": "%s_%s" % (scan.endpoint.url.computed_domain, impact),
                "protocol": scan.endpoint.protocol,
                "port": scan.endpoint.port,
                "type": scan.type,
                "header": "report_header_%s" % scan.type,
                "ip_version": scan.endpoint.ip_version,
                "explanation": calculation.get("explanation", ""),
                "high": calculation.get("high", 0),
                "medium": calculation.get("medium", 0),
                "low": calculation.get("low", 0),
                "impact": impact,
                "color": color,
                "sort_impact": sort_impact,
                "rescan_cost": rescan_cost,
                "last_scan_humanized": naturaltime(scan.last_scan_moment),
                "last_scan_moment": scan.last_scan_moment.isoformat(),
                "last_scan_moment_python": scan.last_scan_moment,
                "being_rescanned": scan.id in endpoint_rescanned_ids,
            })

    # sort the scans, so url and endpointscans mingle correctly
    all_scans_view = sorted(all_scans_view, key=lambda k: (k['domain'], k['sort_impact']))

    return render(request, 'pro/issues.html', {'latest_scans': all_scans_view,
                                               'credits': account.credits,
                                               'rescan_requests': rescan_requests,
                                               'account': account})


@login_required(login_url='/pro/login/?next=/pro/')
def account(request):
    this_account = getAccount(request)

    transactions = CreditMutation.objects.all().filter(account=this_account)

    return render(request, 'pro/account.html', {'transactions': transactions,
                                                'credits': this_account.credits})


@login_required(login_url='/pro/login/?next=/pro/')
def portfolio(request):
    account = getAccount(request)
    return render(request, 'pro/portfolio.html', {'account': account})


def portfolio_data(request):

    one_year_ago = datetime.now(pytz.utc) - timedelta(days=365)

    report_statistics = UrlListReport.objects.filter(when__gte=one_year_ago).only(
        'when', 'total_endpoints', 'total_urls', 'high', 'medium', 'low').order_by('when')
    urllists = UrlList.objects.all().filter(
        account=getAccount(request)
    ).prefetch_related(
        'urls',
        Prefetch('urllistreport_set', queryset=report_statistics),
        # it's NOT POSSIBLE to get the latest report in a select related statement. Latest doens't return a queryset,
        # aggegrate doesn't return a queryset. Slicing is not allowed, and getting all reports is nonsense.
        # latest_report = UrlListReport.objects.annotate(max_id=Max('id')).filter(id=F('max_id')).only('calculation')
        # Prefetch('urllistreport_set', queryset=latest_report, to_attr='report')
    )

    data = []

    for urllist in urllists:

        # getting the latest report manually, which is unacceptable. i mean wtf!
        # latest_report = UrlListReport.objects.all().filter(urllist=urllist).only('calculation').latest('when')
        # not displaying this yet...

        stats = []
        urls = []

        for url in urllist.urls.all():
            urls.append({
                'url': url.url,
                'created_on': url.created_on,
                'resolves': not url.not_resolvable,
                'is_dead': url.is_dead
            })

        for report in urllist.urllistreport_set.all():
            stats.append({
                'date': report.when.date().isoformat(),
                'urls': report.total_urls,
                'endpoints': report.total_endpoints,
                'high': report.high,
                'medium': report.medium,
                'low': report.low
            })

        data.append({
            'name': urllist.name,
            'name_slug': slugify(urllist.name),
            'stats': stats,
            'urls': urls,
            # 'report': latest_report.calculation
            # todo: add mail options.
        })

    return JsonResponse(data, encoder=JSEncoder, safe=False)


@login_required(login_url='/pro/login/?next=/pro/')
def mail(request):
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

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
from websecmap.pro.forms import MailSignupForm
from websecmap.pro.logic.shared import get_account, has_account
from websecmap.pro.models import Account, CreditMutation, ProUser, RescanRequest, UrlList, UrlListReport
from websecmap.reporting.severity import get_severity
from websecmap.scanners import ALL_SCAN_TYPES, ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan

log = logging.getLogger(__package__)

LOGIN_URL = "/pro/login/?next=/pro/"


@login_required(login_url=LOGIN_URL)
def dummy(request):
    return JsonResponse({"hello": "world"}, encoder=JSEncoder)


@login_required(login_url=LOGIN_URL)
def home(request):
    if not has_account(request):
        return render(request, "pro/error.html", {"message": "This user does not have a pro account associated."})

    account = get_account(request)

    user = User.objects.all().filter(pk=request.user.id).first()
    prouser = ProUser.objects.all().filter(user=request.user).first()

    accounts = []
    user_is_staff = False

    # some real hot classic old school programming right here
    if user.is_staff:
        user_is_staff = True
        accounts = list(Account.objects.all().values("id", "name"))

        # you'll get the first entry in the querydict
        if request.POST.get("change_account", None):
            # don't know how inheritance works with user, i think it's ugly.
            prouser.account = Account.objects.get(id=request.POST.get("change_account"))
            prouser.save()

    return render(
        request,
        "pro/home.html",
        {
            "admin": settings.ADMIN,
            "debug": settings.DEBUG,
            "account": account,
            "user_is_staff": user_is_staff,
            "accounts": accounts,
            "selected_account": prouser.account.id,
        },
    )


def signup(request):

    if request.POST:
        form = MailSignupForm(request.POST)

        if form.is_valid():
            form.save()
            return render(request, "pro/registration/signup_success.html")

    else:
        form = MailSignupForm()

    return render(request, "pro/registration/signup.html", {"form": form})


def rescan_costs(scan):
    calculation = get_severity(scan)

    cost = (
        100
        if calculation.get("high", 0)
        else 50
        if calculation.get("medium", 0)
        else 20
        if calculation.get("low", 0)
        else 10
    )

    return cost


def issue_data(request, list_name: str = ""):
    all_scans_view = []

    account = get_account(request)

    rescan_requests = list(RescanRequest.objects.all().filter(account=account).exclude(status="finished"))
    endpoint_rescanned_ids = [x.scan_id for x in rescan_requests if x.scan_type in ENDPOINT_SCAN_TYPES]
    url_rescanned_ids = [x.scan_id for x in rescan_requests if x.scan_type in URL_SCAN_TYPES]

    if list_name:
        latest_endpoint_scans = EndpointGenericScan.objects.all().filter(endpoint__url__urllist__name=list_name)
        latest_url_scans = UrlGenericScan.objects.all().filter(url__urllist__name=list_name)
    else:
        latest_endpoint_scans = EndpointGenericScan.objects.all()
        latest_url_scans = UrlGenericScan.objects.all()

    latest_endpoint_scans = (
        latest_endpoint_scans.filter(
            endpoint__url__urllist__account=account, type__in=ENDPOINT_SCAN_TYPES, is_the_latest_scan=True
        )
        .order_by("-rating_determined_on")
        .select_related("endpoint", "endpoint__url")
    )

    latest_url_scans = (
        latest_url_scans.filter(url__urllist__account=account, type__in=URL_SCAN_TYPES, is_the_latest_scan=True)
        .order_by("-rating_determined_on")
        .select_related("url")
    )

    latest_scans = list(latest_url_scans) + list(latest_endpoint_scans)

    for scan in latest_scans:
        calculation = get_severity(scan)

        impact = (
            "high"
            if calculation.get("high", 0)
            else "medium"
            if calculation.get("medium", 0)
            else "low"
            if calculation.get("low", 0)
            else "ok"
        )

        # don't show things that are fine.
        if impact == "ok":
            continue

        color = (
            "#ff455833"
            if calculation.get("high", 0)
            else "#ff9a4533"
            if calculation.get("medium", 0)
            else "#fffc4533"
            if calculation.get("low", 0)
            else "#a2f59633"
        )

        sort_impact = (
            0
            if calculation.get("high", 0)
            else 1
            if calculation.get("medium", 0)
            else 2
            if calculation.get("low", 0)
            else 3
        )

        # todo: this should be standardized somewhere.
        rescan_cost = rescan_costs(scan)

        if scan.type in URL_SCAN_TYPES:
            # url scans
            all_scans_view.append(
                {
                    "id": scan.id,
                    "url": scan.url.url,
                    "service": scan.url.url,
                    "domain": scan.url.computed_domain,
                    "domain_and_impact": "%s_%s" % (scan.url.computed_domain, impact),
                    "protocol": scan.type,
                    "type": scan.type,
                    "header": scan.type.replace("_", " ").title(),
                    "port": "-",
                    "ip_version": "-",
                    "explanation": calculation.get("explanation", ""),
                    "is_explained": calculation.get("is_explained", False),
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
                    "unique_id": "%s%s" % (scan.type, scan.id),
                }
            )
        else:
            # endpoint scans
            all_scans_view.append(
                {
                    "id": scan.id,
                    "url": scan.endpoint.url.url,
                    "service": "%s/%s (IPv%s)" % (scan.endpoint.protocol, scan.endpoint.port, scan.endpoint.ip_version),
                    "domain": scan.endpoint.url.computed_domain,
                    "domain_and_impact": "%s_%s" % (scan.endpoint.url.computed_domain, impact),
                    "protocol": scan.endpoint.protocol,
                    "port": scan.endpoint.port,
                    "type": scan.type,
                    "header": scan.type.replace("_", " ").title(),
                    "ip_version": scan.endpoint.ip_version,
                    "explanation": calculation.get("explanation", ""),
                    "is_explained": calculation.get("is_explained", False),
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
                    "unique_id": "%s%s" % (scan.type, scan.id),
                }
            )

    # sort the scans, so url and endpointscans mingle correctly
    all_scans_view = sorted(all_scans_view, key=lambda k: (k["domain"], k["sort_impact"]))

    return JsonResponse({"issues": all_scans_view}, encoder=JSEncoder, safe=False)


@login_required(login_url=LOGIN_URL)
def issues(request):
    this_account = get_account(request)

    return render(request, "pro/issues.html", {"account": this_account, "credits": this_account.credits})


@login_required(login_url=LOGIN_URL)
def account(request):
    this_account = get_account(request)

    transactions = CreditMutation.objects.all().filter(account=this_account)

    return render(request, "pro/account.html", {"transactions": transactions, "credits": this_account.credits})


@login_required(login_url=LOGIN_URL)
def portfolio(request):
    account = get_account(request)
    return render(request, "pro/portfolio.html", {"account": account})


def portfolio_data(request):

    one_year_ago = datetime.now(pytz.utc) - timedelta(days=365)

    report_statistics = (
        UrlListReport.objects.filter(at_when__gte=one_year_ago)
        .only("at_when", "total_endpoints", "total_urls", "high", "medium", "low")
        .order_by("at_when")
    )

    urllists = (
        UrlList.objects.all()
        .filter(account=get_account(request))
        .prefetch_related(
            "urls",
            Prefetch("urllistreport_set", queryset=report_statistics),
            # it's NOT POSSIBLE to get the latest report in a select related statement. Latest doens't
            # return a queryset,
            # aggegrate doesn't return a queryset. Slicing is not allowed, and getting all reports is nonsense.
            # latest_report = \
            #   UrlListReport.objects.annotate(max_id=Max('id')).filter(id=F('max_id')).only('calculation')
            # Prefetch('urllistreport_set', queryset=latest_report, to_attr='report')
        )
    )

    data = []

    for urllist in urllists:

        # getting the latest report manually, which is unacceptable. i mean wtf!
        # latest_report = UrlListReport.objects.all().filter(urllist=urllist).only('calculation').latest('at_when')
        # not displaying this yet...

        stats = []
        urls = []

        for url in urllist.urls.all():
            urls.append(
                {
                    "url": url.url,
                    "created_on": url.created_on,
                    "resolves": not url.not_resolvable,
                    "is_dead": url.is_dead,
                }
            )

        for report in urllist.urllistreport_set.all():
            stats.append(
                {
                    "date": report.at_when.date().isoformat(),
                    "urls": report.total_urls,
                    "endpoints": report.total_endpoints,
                    "high": report.high,
                    "medium": report.medium,
                    "low": report.low,
                }
            )

        data.append(
            {
                "name": urllist.name,
                "name_slug": slugify(urllist.name),
                "stats": stats,
                "urls": urls,
                # 'report': latest_report.calculation
                # todo: add mail options.
            }
        )

    return JsonResponse(data, encoder=JSEncoder, safe=False)


@login_required(login_url=LOGIN_URL)
def mail(request):
    return render(request, "pro/urls.html", {})


# todo: should also be able to rescan directly from e-mail, which should not require a login.
# this should be done with a special code or something that is unique per finding and cannot be guessed :)
# todo: how to prevent re-queue-ing? How to log a scan request / follow a performed scan?
# todo: create a "rescan all" option.
# todo: check if scan already is requested.
@login_required(login_url=LOGIN_URL)
def rescan_request(request, scan_type, scan_id):

    account = get_account(request)

    if scan_type not in ALL_SCAN_TYPES:
        log.debug("No valid scan type.")
        return error_response("Could not create rescan request.")

    if RescanRequest.objects.all().filter(scan_type=scan_type, scan_id=scan_id).exclude(status="finished").exists():
        log.debug("Scan request already exists.")
        return error_response("A scan request for this scan was already made.")

    scan = None
    url = None
    endpoint = None
    if scan_type in ENDPOINT_SCAN_TYPES:
        try:
            scan = (
                EndpointGenericScan.objects.all()
                .filter(pk=scan_id, is_the_latest_scan=True, endpoint__url__urllist__account=account)
                .prefetch_related("endpoint", "endpoint__url")
                .get()
            )
            endpoint = scan.endpoint
            url = scan.endpoint.url
        except EndpointGenericScan.DoesNotExist:
            log.debug("Not a valid ENDPOINT scan ID, not in this account or not the latest scan.")
            return error_response("Could not create rescan request.")
    else:
        if scan_type in URL_SCAN_TYPES:
            try:
                scan = (
                    UrlGenericScan.objects.all()
                    .filter(pk=scan_id, is_the_latest_scan=True, url__urllist__account=account)
                    .get()
                )
                url = scan.url
            except EndpointGenericScan.DoesNotExist:
                log.debug("Not a valid URL scan ID, not in this account or not the latest scan.")
                return error_response("Could not create rescan request.")

    if not scan or not url:
        log.debug("No scan found on this ID.")
        return error_response("Could not create rescan request.")

    # now what? :)
    # log the rescan somewhere, so it can be followed up.
    # should be picked up in a matter of seconds, as high priority. Will be handled by a separate worker thus splitting
    # the UI from the scanning implementation.
    # placing it in a table also allows more efficient bulk-scanning.

    # todo: cost values
    cost = rescan_costs(scan)

    if not account.can_spend(cost):
        return error_response("Not enough credits.")

    try:
        account.spend_credits(cost, "Requested re-scan of %s on type %s." % (url, scan_type))
    except ValueError:
        return error_response("Not enough credits.")

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

    data = {
        "success": True,
        "message": "Rescan added to queue. The scan will be performed with the highest priority.",
        "error": False,
        "cost": cost,
    }

    return JsonResponse(data, encoder=JSEncoder)


def empty_response():
    return JsonResponse({}, encoder=JSEncoder)


def error_response(message):
    return JsonResponse({"error": True, "message": message, "success": False, "cost": 0}, encoder=JSEncoder)

from datetime import datetime

import pytz
from constance import config
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.contrib.syndication.views import Feed
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext as _

from websecmap.map.logic.map_defaults import remark
from websecmap.organizations.models import Organization
from websecmap.reporting.severity import get_severity
from websecmap.scanners import ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan


class UpdatesOnOrganizationFeed(Feed):

    link = "/data/updates_on_organization_feed/"
    description = "Update feed."

    def title(self, organization_id):
        try:
            organization = Organization.objects.all().filter(pk=organization_id).get()
        except ObjectDoesNotExist:
            return "Organization Updates"

        return "%s Updates" % organization.name

    # it seems weird to do this.
    def get_object(self, request, *args, **kwargs):
        return kwargs.get('organization_id', 0)

    # second parameter via magic
    def items(self, organization_id):
        return latest_updates(organization_id).get("scans", [])

    def item_title(self, item):
        rating = _("Perfect") if not any([item['high'], item['medium'], item['low']]) else \
            _("High") if item['high'] else _("Medium") if item['medium'] else _("Low")

        badge = "✅" if not any([item['high'], item['medium'], item['low']]) else \
            "🔴" if item['high'] else "🔶" if item['medium'] else "🍋"

        return "%s %s - %s: %s" % (badge, rating, item["url"], item["service"])

    def item_description(self, item):
        return "%s: %s" % (_(item["scan_type"]), _(item.get("explanation", "")))

    def item_pubdate(self, item):
        return item["rating_determined_on"]

    # item_link is only needed if NewsItem has no get_absolute_url method.
    # unique links are required to properly display a feed.
    def item_link(self, item):
        return "%s/#report-%s/%s/%s/%s" % \
               (config.PROJECT_WEBSITE,
                item["organization_id"], item["url"], item["service"], item["rating_determined_on"])


class LatestScanFeed(Feed):
    """
        Setting a parameter such as self.scan_type in the get_object will cause concurrency problems.

        The manual is lacking how to get variables to the item_title and such functions: only to "items" it is somewhat
        clear. This is probably because i don't know enough python. Why would this extra parameter work at the "items"
        functions but not anywhere else? (signature issues).
    """

    description = "Overview of the latest scans."

    # magic
    def get_object(self, request, *args, **kwargs):
        # print("args: %s" % kwargs['scan_type'])
        return kwargs.get('scan_type', '')

    def title(self, scan_type: str = ""):
        if scan_type:
            return "%s Scan Updates" % scan_type
        else:
            return "Vulnerabilities Feed"

    def link(self, scan_type: str = ""):
        if scan_type:
            return "/data/feed/%s" % scan_type
        else:
            return "/data/feed/"

    # second parameter via magic
    def items(self, scan_type):
        # print(scan_type)
        if scan_type in ENDPOINT_SCAN_TYPES:
            return EndpointGenericScan.objects.filter(type=scan_type).order_by('-last_scan_moment')[0:30]

        if scan_type in URL_SCAN_TYPES:
            return UrlGenericScan.objects.filter(type=scan_type).order_by('-last_scan_moment')[0:30]

    def item_title(self, item):
        calculation = get_severity(item)
        if not calculation:
            return ""

        rating = _("Perfect") if not any([calculation['high'], calculation['medium'], calculation['low']]) else \
            _("High") if calculation['high'] else _("Medium") if calculation['medium'] else _("Low")

        badge = "✅" if not any([calculation['high'], calculation['medium'], calculation['low']]) else \
            "🔴" if calculation['high'] else "🔶" if calculation['medium'] else "🍋"

        if item.type in URL_SCAN_TYPES:
            # url generic scan:
            return "%s %s - %s" % (badge, rating, item.url.url)
        else:
            # endpoint scan
            return "%s %s - %s" % (badge, rating, item.endpoint.url.url)

    def item_description(self, item):
        calculation = get_severity(item)
        return _(calculation.get("explanation", ""))

    def item_pubdate(self, item):
        return item.last_scan_moment

    # item_link is only needed if NewsItem has no get_absolute_url method.
    def item_link(self, item):
        if item.type in URL_SCAN_TYPES:
            # url generic scan:
            return "%s/#updates/%s/%s" % (config.PROJECT_WEBSITE, item.last_scan_moment, item.url.url)
        else:
            # endpoint scan
            return "%s/#updates/%s/%s" % (config.PROJECT_WEBSITE, item.last_scan_moment, item.endpoint.url.url)


def latest_updates(organization_id):
    """

    :param request:
    :param organization_id: the id will always be "correct", whereas name will have all kinds of terribleness:
    multiple organizations that have the same name in different branches, organizations with generic names etc.
    Finding an organization by name is tricky. Therefore ID.

    We're not filtering any further: given this might result in turning a blind eye to low or medium vulnerabilities.
    :return:
    """

    try:
        # todo: check that the organization is displayed on the map
        organization = Organization.objects.all().filter(pk=organization_id).get()
    except ObjectDoesNotExist:
        return {}

    dataset = {
        "scans": [],
        "render_date": datetime.now(pytz.utc).isoformat(),
        "remark": remark,
    }

    # semi-union, given not all columns are the same. (not python/django-esque solution)
    generic_endpoint_scans = list(EndpointGenericScan.objects.filter(
        endpoint__url__organization=organization,
        type__in=ENDPOINT_SCAN_TYPES
    ).order_by('-rating_determined_on')[0:60])
    url_endpoint_scans = list(UrlGenericScan.objects.filter(
        url__organization=organization,
        type__in=URL_SCAN_TYPES
    ).order_by('-rating_determined_on')[0:60])

    scans = generic_endpoint_scans + url_endpoint_scans

    scans = sorted(scans, key=lambda k: getattr(k, 'rating_determined_on', datetime.now(pytz.utc)), reverse=True)

    for scan in scans:
        scan_type = scan.type
        calculation = get_severity(scan)
        if scan_type in URL_SCAN_TYPES:
            # url scans
            dataset["scans"].append({
                "organization": organization.name,
                "organization_id": organization.pk,
                "url": scan.url.url,
                "service": "%s" % scan.url.url,
                "protocol": scan_type,
                "port": "",
                "ip_version": "",
                "scan_type": scan_type,
                "explanation": calculation.get("explanation", ""),  # sometimes you dont get one.
                "high": calculation.get("high", 0),
                "medium": calculation.get("medium", 0),
                "low": calculation.get("low", 0),
                "rating_determined_on_humanized": naturaltime(scan.rating_determined_on),
                "rating_determined_on": scan.rating_determined_on,
                "last_scan_humanized": naturaltime(scan.last_scan_moment),
                "last_scan_moment": scan.last_scan_moment.isoformat()
            })

        else:
            # endpoint scans
            dataset["scans"].append({
                "organization": organization.name,
                "organization_id": organization.pk,
                "url": scan.endpoint.url.url,
                "service": "%s/%s (IPv%s)" % (scan.endpoint.protocol, scan.endpoint.port, scan.endpoint.ip_version),
                "protocol": scan.endpoint.protocol,
                "port": scan.endpoint.port,
                "ip_version": scan.endpoint.ip_version,
                "scan_type": scan_type,
                "explanation": calculation.get("explanation", ""),  # sometimes you dont get one.
                "high": calculation.get("high", 0),
                "medium": calculation.get("medium", 0),
                "low": calculation.get("low", 0),
                "rating_determined_on_humanized": naturaltime(scan.rating_determined_on),
                "rating_determined_on": scan.rating_determined_on,
                "last_scan_humanized": naturaltime(scan.last_scan_moment),
                "last_scan_moment": scan.last_scan_moment.isoformat()
            })

    return dataset

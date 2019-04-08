from constance import config
from django.contrib.syndication.views import Feed
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext as _

from websecmap.map.views import latest_updates
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

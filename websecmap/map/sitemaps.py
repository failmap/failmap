# https://docs.djangoproject.com/en/5.0/ref/contrib/sitemaps/

from datetime import datetime, timezone
from django.contrib.sitemaps import Sitemap
from websecmap.map.models import Configuration
from websecmap.organizations.models import Organization
from websecmap.scanners.scanner import q_configurations_to_display


class ReportSiteMap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return (
            Organization.objects.all()
            .filter(
                # only organizations that are actually displayed
                q_configurations_to_display("organization"),
                is_dead=False,
            )
            .order_by("id")
        )

    def lastmod(self, obj):
        return datetime.now(timezone.utc).date()

    def location(self, item):
        # always the first layer, which is usually more recognizable than layers that are added later
        first_layer = item.layers.order_by("id").first()
        return (
            f"/report/{item.country}/{first_layer}/{item.id}/?slug={item.computed_name_slug}"
            if first_layer
            else f"/report/{item.id}/?slug={item.computed_name_slug}"
        )


class ConfigurationSiteMap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        return Configuration.objects.all().filter(is_displayed=True)

    def lastmod(self, obj):
        return datetime.now(timezone.utc).date()

    def location(self, item):
        return f"/map/{item.country}/{item.organization_type.name}/"


class ChartSiteMap(ConfigurationSiteMap):
    def location(self, item):
        return f"/charts/{item.country}/{item.organization_type.name}/"


class LoginPlazaSiteMap(ConfigurationSiteMap):
    def location(self, item):
        return f"/login-plaza/{item.country}/{item.organization_type.name}/"


class StatisticsSiteMap(ConfigurationSiteMap):
    def location(self, item):
        return f"/statistics/{item.country}/{item.organization_type.name}/"


class StaticSiteMap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        return ["home", "about", "contact", "faq", "privacy", "terms"]

    def location(self, item):
        return {
            "tracking-cookies": "/tracking-cookies/",
            "leaderboard": "/leaderboard/",
            "about": "/about/",
            "home": "/",
            "datasets": "/datasets/",
            "": "/",
        }.get(item, "")

    def lastmod(self, obj):
        return datetime.now(timezone.utc).date()

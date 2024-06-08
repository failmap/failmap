# https://docs.djangoproject.com/en/5.0/ref/contrib/sitemaps/

from datetime import datetime, timezone
from django.contrib.sitemaps import Sitemap
from websecmap.map.models import Configuration
from websecmap.organizations.models import Organization


class ReportSiteMap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return Organization.objects.all().filter(is_dead=False)

    def lastmod(self, obj):
        return datetime.now(timezone.utc).date()

    def location(self, obj):
        first_layer = obj.layers.first()
        return (
            f"/report/{obj.country}/{first_layer}/{obj.id}/?slug={obj.computed_name_slug}"
            if first_layer
            else f"/report/{obj.id}/?slug={obj.computed_name_slug}"
        )


class ConfigurationSiteMap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        return Configuration.objects.all().filter(is_displayed=True)

    def lastmod(self, obj):
        return datetime.now(timezone.utc).date()

    def location(self, obj):
        return f"/map/{obj.country}/{obj.organization_type.name}/"


class ChartSiteMap(ConfigurationSiteMap):
    def location(self, obj):
        return f"/charts/{obj.country}/{obj.organization_type.name}/"


class LoginPlazaSiteMap(ConfigurationSiteMap):
    def location(self, obj):
        return f"/login-plaza/{obj.country}/{obj.organization_type.name}/"


class StatisticsSiteMap(ConfigurationSiteMap):
    def location(self, obj):
        return f"/statistics/{obj.country}/{obj.organization_type.name}/"


class StaticSiteMap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        return ["home", "about", "contact", "faq", "privacy", "terms"]

    def location(self, obj):
        return {
            "tracking-cookies": "/tracking-cookies/",
            "leaderboard": "/leaderboard/",
            "about": "/about/",
            "home": "/",
            "datasets": "/datasets/",
            "": "/",
        }.get(obj, "")

    def lastmod(self, obj):
        return datetime.now(timezone.utc).date()

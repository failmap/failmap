import logging
from datetime import datetime

import pytz
from django.contrib import admin
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.urls import reverse
from django.utils.html import format_html
from jet.admin import CompactInline

import failmap.scanners.scanner_http as scanner_http
from failmap.map.rating import OrganizationRating, UrlRating, rate_organization_on_moment
from failmap.scanners.admin import UrlIpInline
from failmap.scanners.models import Endpoint
from failmap.scanners.onboard import onboard_urls
from failmap.scanners.scanner_dns import brute_known_subdomains, certificate_transparency, nsec
from failmap.scanners.scanner_plain_http import scan_urls as plain_http_scan_urls
from failmap.scanners.scanner_screenshot import screenshot_urls
from failmap.scanners.scanner_security_headers import scan_urls as security_headers_scan_urls
from failmap.scanners.scanner_tls_qualys import scan_urls as tls_qualys_scan_urls

from ..app.models import Job
from ..celery import PRIO_HIGH
from .models import Coordinate, Organization, OrganizationType, Promise, Url

logger = logging.getLogger(__name__)


PROMISE_DESCRIPTION = """
<p>A 'promise' is an indication by an organisation representitive that an improvement
has been made which will alter the organizations score. A generic message will be
displayed on the organization report with the creation and expiry date of the promise
until it expires.</p>
<p>This indication is to overcome the problem of a negative score even though improvement
are made, but the score cannot reflect them yet due to technical or bureaucratic reasons.</p>
<p>It is not intended for long term promises of improvement that have not been applied or
put in to progress. The promised improvement must be verifiable by Faalkaart within a
handfull of days.</p>
"""


class UrlAdminInline(CompactInline):
    model = Url
    extra = 0
    show_change_link = True


class EndpointAdminInline(CompactInline):
    model = Endpoint
    extra = 0
    show_change_link = True
    ordering = ["is_dead"]


class CoordinateAdminInline(CompactInline):
    model = Coordinate
    extra = 0


class OrganizationRatingAdminInline(CompactInline):
    model = OrganizationRating
    extra = 0
    ordering = ["-when"]


class UrlRatingAdminInline(CompactInline):
    model = UrlRating
    extra = 0
    ordering = ["-when"]


class PromiseAdminInline(CompactInline):
    model = Promise
    extra = 0
    ordering = ["-created_on"]

    fieldsets = (
        (None, {
            'fields': ('organization', 'created_on', 'expires_on', 'notes'),
            'description': PROMISE_DESCRIPTION,
        }),
    )


class OrganizationAdmin(admin.ModelAdmin):
    class Media:
        js = ('js/action_buttons.js', )

    list_display = ('name', 'type', 'country')
    search_fields = (['name', 'country', 'type__name'])
    list_filter = ('name', 'type__name', 'country')  # todo: type is now listed as name, confusing
    fields = ('name', 'type', 'country', 'twitter_handle')

    inlines = [UrlAdminInline, CoordinateAdminInline, OrganizationRatingAdminInline, PromiseAdminInline]  #

    # actions = ['rate_organization', 'scan_organization']

    def rate_organization(self, request, queryset):

        for organization in queryset:
            rate_organization_on_moment(organization=organization)

        self.message_user(request, "Organization(s) have been rated")

    def scan_organization(self, request, queryset):
        urls = Url.objects.filter(organization__in=list(queryset))
        tls_qualys_scan_urls(list(urls))
        self.message_user(request, "Organization(s) have been scanned")

    rate_organization.short_description = \
        "Rate selected Organizations based on available scansresults"

    scan_organization.short_description = \
        "Scan selected Organizations"


class UrlAdmin(admin.ModelAdmin):
    class Media:
        js = ('js/action_buttons.js', )

    list_display = ('url', 'endpoints', 'current_rating', 'onboarded', 'uses_dns_wildcard',
                    'dead_for', 'unresolvable_for', 'created_on')
    search_fields = ('url', )
    list_filter = ('url', 'is_dead', 'is_dead_since', 'is_dead_reason',
                   'not_resolvable', 'not_resolvable_since', 'not_resolvable_reason',
                   'uses_dns_wildcard', 'organization')

    fieldsets = (
        (None, {
            'fields': ('url', 'organization', 'created_on', 'onboarded')
        }),
        ('DNS', {
            'fields': ('uses_dns_wildcard', ),
        }),
        ('Resolvability', {
            'fields': ('not_resolvable', 'not_resolvable_since', 'not_resolvable_reason'),
        }),
        ('dead URL management', {
            'fields': ('is_dead', 'is_dead_since', 'is_dead_reason'),
        }),
    )
    readonly_fields = ['created_on', 'onboarded']

    def endpoints(self, obj: Url):

        return format_html("%s <a href='/admin/scanners/endpoint/?q=%s' target='_blank'>🔍</a>" %
                           (obj.endpoint_set.count(), obj.url))

    @staticmethod
    def unresolvable_for(self):
        if self.not_resolvable and self.not_resolvable_since:
            return naturaltime(self.not_resolvable_since)
        else:
            return "-"

    # todo: further humanize this.
    @staticmethod
    def dead_for(self):
        if self.is_dead and self.is_dead_since:
            return naturaltime(self.is_dead_since)
        else:
            return "-"

    @staticmethod
    def current_rating(obj):
        return UrlRating.objects.filter(url=obj).latest('when').rating

    inlines = [EndpointAdminInline, UrlRatingAdminInline, UrlIpInline]

    actions = []

    def onboard(self, request, queryset):
        onboard_urls(urls=list(queryset))
        self.message_user(request, "URL(s) have been scanned on known subdomains: Done")
    actions.append('onboard')
    onboard.short_description = "🔮  Onboard (discover subdomains and endpoints, http scans, screenshot)"

    def dns_certificate_transparency(self, request, queryset):
        certificate_transparency(urls=list(queryset))
        self.message_user(request, "URL(s) have been scanned on known subdomains: Done")
    actions.append('dns_certificate_transparency')
    dns_certificate_transparency.short_description = "🗺  +subdomains (certificate transparency)"

    def dns_known_subdomains(self, request, queryset):
        brute_known_subdomains(urls=list(queryset))
        self.message_user(request, "Discover subdomains (using known subdomains): Done")
    dns_known_subdomains.short_description = "🗺  +subdomains (known subdomains)"
    actions.append('dns_known_subdomains')

    def dns_nsec(self, request, queryset):
        nsec(urls=list(queryset))
        self.message_user(request, "Discover subdomains (using nsec): Done")
    dns_known_subdomains.short_description = "🗺  +subdomains (nsec)"
    actions.append('dns_nsec')

    def discover_http_endpoints(self, request, queryset):
        scanner_http.discover_endpoints(urls=list(queryset))
        self.message_user(request, "Discover http(s) endpoints: Done")
    discover_http_endpoints.short_description = "🗺  Discover http(s) endpoints"
    actions.append('discover_http_endpoints')

    def scan_tls_qualys(self, request, queryset):
        # create a celery task and use Job object to keep track of the status
        urls = list(queryset)
        task = tls_qualys_scan_urls(urls=urls, execute=False)
        name = "Scan TLS Qualys (%s) " % str(urls)
        job = Job.create(task, name, request, priority=PRIO_HIGH)
        link = reverse('admin:app_job_change', args=(job.id,))
        self.message_user(request, '%s: job created, id: <a href="%s">%s</a>' % (name, link, str(job)))
    scan_tls_qualys.short_description = "🔬  Scan TLS Qualys"
    actions.append('scan_tls_qualys')

    def security_headers(self, request, queryset):
        # create a celery task and use Job object to keep track of the status
        urls = list(queryset)
        task = security_headers_scan_urls(urls=urls, execute=False)
        name = "Scan Security Headers (%s) " % str(urls)
        job = Job.create(task, name, request, priority=PRIO_HIGH)
        link = reverse('admin:app_job_change', args=(job.id,))
        self.message_user(request, '%s: job created, id: <a href="%s">%s</a>' % (name, link, str(job)))
    security_headers.short_description = "🔬  Scan Security Headers"
    actions.append('security_headers')

    def plain_http_scan(self, request, queryset):
        urls = list(queryset)
        task = plain_http_scan_urls(urls=urls, execute=False)
        name = "Scan Plain Http (%s) " % str(urls)
        job = Job.create(task, name, request, priority=PRIO_HIGH)
        link = reverse('admin:app_job_change', args=(job.id,))
        self.message_user(request, '%s: job created, id: <a href="%s">%s</a>' % (name, link, str(job)))
    plain_http_scan.short_description = "🔬  Scan Plain Http"
    actions.append('plain_http_scan')

    def screenshots(self, request, queryset):
        screenshot_urls([url for url in queryset])
        self.message_user(request, "Create screenshot: Done")
    screenshots.short_description = "📷  Create screenshot"
    actions.append('screenshots')

    # suspended, since adding ratings and rebuild ratings don't produce 100% the same results.
    # def rate_url(self, request, queryset):
    #     add_url_rating([url for url in queryset])
    #     self.message_user(request, "Rate Url: done")
    # rate_url.short_description = "✅  Rate Url"
    # actions.append('rate_url')

    # suspended, since adding ratings and rebuild ratings don't produce 100% the same results.
    # def rate_organization_(self, request, queryset):
    #     # a queryset doesn't have the "name" property...
    #     for url in queryset:
    #         for organization in url.organization.all():
    #             rate_organization_on_moment(organization)
    #     self.message_user(request, "Rate Organization: done")
    # rate_organization_.short_description = "✅  Rate Organization"
    # actions.append('rate_organization_')

    def declare_dead(self, request, queryset):
        for url in queryset:
            url.is_dead = True
            url.is_dead_reason = "Killed via admin interface"
            url.is_dead_since = datetime.now(pytz.utc)
            url.save()
        self.message_user(request, "Declare dead: Done")
    declare_dead.short_description = "🔪  Declare dead"
    actions.append('declare_dead')

    def timeline_debug(self, request, queryset):
        from failmap.map.rating import create_timeline, show_timeline_console
        from django.http import HttpResponse

        content = "<pre>"
        for url in queryset:
            content += show_timeline_console(create_timeline(url), url)

        content += "</pre>"

        return HttpResponse(content)
    timeline_debug.short_description = "🐞  Timeline"
    actions.append('timeline_debug')


class OrganizationTypeAdmin(admin.ModelAdmin):
    list_display = ('name', )
    search_fields = ('name', )
    list_filter = ('name', )
    fields = ('name', )


class CoordinateAdmin(admin.ModelAdmin):
    list_display = ('organization', 'geojsontype')
    search_fields = ('organization', 'geojsontype')
    list_filter = ('organization', 'geojsontype')
    fields = ('organization', 'geojsontype', 'area')


class PromiseAdmin(admin.ModelAdmin):
    list_display = ('organization', 'created_on', 'expires_on')
    search_fields = ('organization',)
    list_filter = ('organization',)

    fieldsets = (
        (None, {
            'fields': ('organization', 'created_on', 'expires_on', 'notes'),
            'description': PROMISE_DESCRIPTION,
        }),
    )


admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Url, UrlAdmin)
admin.site.register(Coordinate, CoordinateAdmin)
admin.site.register(OrganizationType, OrganizationTypeAdmin)
admin.site.register(Promise, PromiseAdmin)

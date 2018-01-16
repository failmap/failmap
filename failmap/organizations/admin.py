import logging
from datetime import datetime

import pytz
from django.contrib import admin
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.urls import reverse
from django.utils.html import format_html
from jet.admin import CompactInline

import failmap.scanners.scanner_http as scanner_http
from failmap import types
from failmap.map import rating
from failmap.map.rating import OrganizationRating, UrlRating
from failmap.scanners import scanner_plain_http, scanner_security_headers, scanner_tls_qualys
from failmap.scanners.admin import UrlIpInline
from failmap.scanners.models import Endpoint
from failmap.scanners.onboard import onboard_urls
from failmap.scanners.scanner_dns import brute_known_subdomains, certificate_transparency, nsec
from failmap.scanners.scanner_screenshot import screenshot_urls

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


class ActionMixin:
    """Generic Mixin to add Admin Button for Organization/Url/Endpoint Actions.

    This class is intended to be added to ModelAdmin classes so all Actions are available without duplicating code.

    Action methods as described in:
      https://docs.djangoproject.com/en/2.0/ref/contrib/admin/actions/#actions-as-modeladmin-methods

    Most actions work on the same primary models (organization,url,endpoint). The Actions don't do any actual work but
    rather compose a task with the provided Queryset. After which this task is scheduled using a Job. This generic
    principle has been implemented in `generic_action` and the specific action implementations (eg; `scan_plain_http`)
    just provide the correct metadata (name, icon) and task composer to call.

    """

    actions = []

    def scan_plain_http(self, *args, **kwargs):
        return self.generic_action(scanner_plain_http.compose_task, 'Scan Plain Http', *args, **kwargs)
    scan_plain_http.short_description = '🔬  Scan Plain Http'
    actions.append(scan_plain_http)

    def scan_security_headers(self, *args, **kwargs):
        return self.generic_action(scanner_security_headers.compose_task, 'Scan Security Headers', *args, **kwargs)
    scan_security_headers.short_description = '🔬  Scan Security Headers'
    actions.append(scan_security_headers)

    def scan_tls_qualys(self, *args, **kwargs):
        return self.generic_action(scanner_tls_qualys.compose_task, 'Scan TLS Qualys', *args, **kwargs)
    scan_tls_qualys.short_description = '🔬  Scan TLS Qualys'
    actions.append(scan_tls_qualys)

    def rebuild_ratings(self, *args, **kwargs):
        return self.generic_action(rating.compose_task, 'Rebuild rating', *args, **kwargs)
    rebuild_ratings.short_description = '✅  Rebuild rating'
    actions.append(rebuild_ratings)

    def generic_action(self, task_composer: types.compose_task, name: str, request, queryset):
        """Admin action that will create a Job of tasks."""

        filters = {'x_filter': {'id__in': queryset.values_list('id')}}
        if queryset.model == Organization:
            filters['organizations_filter'] = filters.pop('x_filter')
        elif queryset.model == Url:
            filters['urls_filter'] = filters.pop('x_filter')
        elif queryset.model == Endpoint:
            filters['endpoints_filter'] = filters.pop('x_filter')

        task = task_composer(**filters)
        task_name = "%s (%s) " % (name, ','.join(map(str, list(queryset))))
        job = Job.create(task, task_name, request, priority=PRIO_HIGH)
        link = reverse('admin:app_job_change', args=(job.id,))
        self.message_user(request, 'Job created, <a href="%s">%s</a>' % (link, task_name))


class OrganizationAdmin(ActionMixin, admin.ModelAdmin):
    list_display = ('name', 'type', 'country')
    search_fields = (['name', 'country', 'type__name'])
    list_filter = ('name', 'type__name', 'country')  # todo: type is now listed as name, confusing
    fields = ('name', 'type', 'country', 'twitter_handle')

    inlines = [UrlAdminInline, CoordinateAdminInline, OrganizationRatingAdminInline, PromiseAdminInline]  #


class UrlAdmin(ActionMixin, admin.ModelAdmin):
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

    def screenshots(self, request, queryset):
        screenshot_urls([url for url in queryset])
        self.message_user(request, "Create screenshot: Done")
    screenshots.short_description = "📷  Create screenshot"
    actions.append('screenshots')

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

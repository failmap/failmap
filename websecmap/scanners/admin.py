import taggit
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from import_export.admin import ImportExportModelAdmin
from jet.admin import CompactInline
from jet.filters import RelatedFieldAjaxListFilter

from websecmap.map.admin import ordering_actions
from websecmap.scanners import models
from websecmap.scanners.models import Endpoint, Product, ProductHierarchy, State, ProductCookieIndicator
from websecmap.scanners.proxy import check_proxy
from websecmap.scanners.scanmanager import delete_metric_and_set_previous_to_latest
from websecmap.scanners.scanner.banners.detect_version import add_excepted_banner_to_config, clean_and_detect
from websecmap.scanners.scanner.internet_nl_websecmap import progress_running_scan, recover_and_retry
from websecmap.scanners.security_policies import (
    apply_security_policy,
    remove_security_policy,
    apply_affects,
    remove_affects,
)
from django_countries import countries


class EndpointGenericScanInline(CompactInline):
    model = models.EndpointGenericScan
    extra = 0
    show_change_link = True


@admin.register(models.UrlIp)
class UrlIpAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("url", "ip", "rdns_name", "discovered_on", "is_unused", "is_unused_since")
    search_fields = ("url__url", "ip", "rdns_name", "discovered_on", "is_unused_since")
    list_filter = ["url", "rdns_name", "discovered_on", "is_unused_since"][::-1]
    fields = ("url", "ip", "rdns_name", "discovered_on", "is_unused", "is_unused_since", "is_unused_reason")
    readonly_fields = ["discovered_on"]


@admin.register(models.SecurityPolicy)
class SecurityPolicyAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = (
        "id",
        "name_",
        "applied",
        "description",
        "common_subdomains",
        "common_protocols",
        "common_ports",
        "common_ip_versions",
        "common_html_front_page_content",
        "affects_which_explain",
    )

    @staticmethod
    def affects_which_explain(obj):
        return "".join(f"{affect}" for affect in obj.affect_explain_scoring_policy.all())

    @staticmethod
    def applied(obj):
        return Endpoint.objects.all().filter(security_policies=obj).count()

    @staticmethod
    def name_(obj):
        return f"{obj.technical_policy_name}: {obj.name}"

    actions = ["apply_policies", "remove_policies", "apply_affect", "remove_affect"]

    def remove_policies(self, request, queryset):
        # only if there are no policies set.
        for item in queryset:
            remove_security_policy(item)

    def apply_policies(self, request, queryset):
        # only if there are no policies set.
        for item in queryset:
            apply_security_policy(item)

    def apply_affect(self, request, queryset):
        affected = 0
        for item in queryset:
            affected = apply_affects(item)
        self.message_user(request, f"Affected {affected} scans.")

    def remove_affect(self, request, queryset):
        affected = 0
        for item in queryset:
            affected = remove_affects(item)
        self.message_user(request, f"Affected {affected} scans.")


@admin.register(models.Endpoint)
class EndpointAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("security_policies")

    list_display = (
        "id",
        "url",
        "origin",
        "sec_policy",
        "visit",
        "discovered_on",
        "ip_version",
        "port",
        "protocol",
        "is_dead",
        "is_dead_since",
        "is_dead_reason",
    )
    search_fields = ("url__url",)
    list_filter = [
        "url__organization__country",
        "url__organization__layers__name",
        "ip_version",
        "port",
        "protocol",
        "is_dead",
        "origin",
        "discovered_on",
        "security_policies",
    ][::-1]
    fieldsets = (
        (None, {"fields": ("url", "security_policies", "ip_version", "protocol", "port", "discovered_on", "origin")}),
        (
            "dead endpoint management",
            {
                "fields": ("is_dead", "is_dead_since", "is_dead_reason"),
            },
        ),
    )

    readonly_fields = ["discovered_on", "origin"]

    @staticmethod
    def sec_policy(obj):
        return ", ".join(o.name for o in obj.security_policies.all())

    @staticmethod
    def visit(inst):
        if not inst:
            return "- no url, how?"
        if inst.url is None:
            url = f"{inst.protocol}://???:{inst.port}/"
        else:
            url = f"{inst.protocol}://{inst.url.url}:{inst.port}/"
        return format_html(f"<a href='{url}' target='_blank'>Visit</a>")

    inlines = [EndpointGenericScanInline]
    save_as = True  # Save as new is nice for duplicating endpoints.


@admin.register(models.TlsQualysScratchpad)
class TlsQualysScratchpadAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("domain", "at_when")
    search_fields = ("domain", "at_when")
    list_filter = ["domain", "at_when"][::-1]
    fields = ("domain", "data")
    readonly_fields = ["at_when"]


@admin.register(models.Screenshot)
class ScreenshotAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("endpoint", "created_on", "filename")
    search_fields = ("endpoint__url__url", "created_on", "filename")
    list_filter = ["endpoint", "created_on", "filename"][::-1]
    fields = ("endpoint", "image", "created_on", "filename", "width_pixels", "height_pixels")
    readonly_fields = ["created_on", "image"]


@admin.register(models.EndpointGenericScan)
class EndpointGenericScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)

        # Because the endpoint, to display, needs url data, it will try to retrieve that for every
        # record. Here we already include those results, so the page loads 10x faster (at okay speeds now)
        qs = qs.prefetch_related(
            "endpoint", "endpoint__url", "endpoint__url__organization", "endpoint__url__organization__type"
        )

        return qs

    list_display = (
        "id",
        "endpoint",
        "type",
        "rating",
        "meaning",
        "evidence",
        "last_scan_moment",
        "rating_determined_on",
        "comply_or_explain_is_explained",
        "explain",
        "is_the_latest_scan",
    )
    search_fields = ("endpoint__url__url",)

    list_filter = [
        "endpoint__url__organization__country",
        "endpoint__url__organization__layers__name",
        "endpoint__url__is_dead",
        "endpoint__url__not_resolvable",
        ("endpoint", RelatedFieldAjaxListFilter),
        "type",
        "rating",
        "last_scan_moment",
        "rating_determined_on",
        "endpoint__protocol",
        "endpoint__port",
        "endpoint__ip_version",
        "endpoint__discovered_on",
        "endpoint__is_dead",
        "comply_or_explain_is_explained",
        "is_the_latest_scan",
    ][::-1]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "endpoint",
                    "type",
                    "rating",
                    "meaning",
                    "explanation",
                    "evidence",
                    "last_scan_moment",
                    "rating_determined_on",
                    "is_the_latest_scan",
                )
            },
        ),
        (
            "comply or explain",
            {
                "fields": (
                    "comply_or_explain_is_explained",
                    "comply_or_explain_explanation_valid_until",
                    "comply_or_explain_explanation",
                    "comply_or_explain_explained_by",
                    "comply_or_explain_explained_on",
                    "comply_or_explain_case_handled_by",
                    "comply_or_explain_case_additional_notes",
                ),
            },
        ),
    )

    # shave off a second and more when there are many results
    show_full_result_count = False

    def explain(self, instance):
        return format_html("<a href='./{}/change/#/tab/module_1/'>Explain</a>", instance.pk)

    readonly_fields = ["last_scan_moment", "meaning"]

    actions = []

    def reevaluate_version(self, request, queryset):
        changed = 0
        for item in queryset:
            if item.type != "bannergrab":
                continue

            change = clean_and_detect(item)
            if change:
                changed += 1

        self.message_user(request, f"Updated {queryset.count()} scans, changed {changed} scans.")

    reevaluate_version.short_description = "🔁  Re-evaluate bannergrab version data"
    actions.append("reevaluate_version")

    def add_version_exception(self, request, queryset):
        for item in queryset:
            if item.type != "bannergrab":
                continue

            add_excepted_banner_to_config(item.evidence)

    add_version_exception.short_description = "Add banner to excepted banners"
    actions.append("add_version_exception")

    def delete_metric_and_set_previous_to_latest_(self, request, queryset):
        for item in queryset:
            delete_metric_and_set_previous_to_latest(item)

    delete_metric_and_set_previous_to_latest_.short_description = "Delete metric and set previous to latest"
    actions.append("delete_metric_and_set_previous_to_latest_")


@admin.register(models.UrlGenericScan)
class UrlGenericScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.prefetch_related("url__organization", "url__organization__type")
        return qs

    list_display = (
        "id",
        "url_",
        "type",
        "rating",
        "explanation",
        "last_scan_moment",
        "rating_determined_on",
        "comply_or_explain_is_explained",
        "explain",
        "is_the_latest_scan",
        "short_evidence",
    )
    search_fields = ("url__url", "type", "rating", "explanation", "last_scan_moment", "rating_determined_on")
    list_filter = [
        "url__organization__country",
        "url__organization__layers__name",
        "type",
        "rating",
        "last_scan_moment",
        "rating_determined_on",
        "comply_or_explain_is_explained",
        "is_the_latest_scan",
    ][::-1]

    @staticmethod
    def url_(obj):
        return mark_safe(f"<a href='/admin/organizations/url/{obj.url.id}/change/'>{obj}</a>")

    @staticmethod
    def short_evidence(obj):
        return obj.evidence[0:60]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "url",
                    "type",
                    "rating",
                    "explanation",
                    "evidence",
                    "last_scan_moment",
                    "rating_determined_on",
                    "is_the_latest_scan",
                )
            },
        ),
        (
            "comply or explain",
            {
                "fields": (
                    "comply_or_explain_is_explained",
                    "comply_or_explain_explanation_valid_until",
                    "comply_or_explain_explanation",
                    "comply_or_explain_explained_by",
                    "comply_or_explain_explained_on",
                    "comply_or_explain_case_handled_by",
                    "comply_or_explain_case_additional_notes",
                ),
            },
        ),
    )

    def explain(self, instance):
        return format_html("<a href='./{}/change/#/tab/module_1/'>Explain</a>", instance.pk)

    readonly_fields = ["last_scan_moment", "rating_determined_on"]


@admin.register(models.EndpointGenericScanScratchpad)
class EndpointGenericScanScratchpadAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("type", "domain", "at_when", "data")
    search_fields = ("type", "domain", "at_when", "data")
    list_filter = ["type", "domain", "at_when", "data"][::-1]
    fields = ("type", "domain", "at_when", "data")


@admin.register(models.InternetNLV2Scan)
class InternetNLV2ScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    # defer retrieved_scan_report and retrieved_scan_report_technical, metadata as those fields are huge and not shown
    # when listing. List display is not a ONLY filter it seems!
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # these fields are loaded during list_display while not needed and taking up a lot of memory
        if request.path == "/admin/scanners/internetnlv2scan/":
            qs = qs.defer("metadata", "retrieved_scan_report", "retrieved_scan_report_technical")
        return qs

    list_display = (
        "id",
        "type",
        "scan_id",
        "online",
        "state",
        "state_message",
        "last_state_check",
        "last_state_change",
        "domains",
    )
    search_fields = ("subject_urls__url", "scan_id")
    list_filter = ("state", "state_message", "last_state_check", "last_state_change", "type")
    fields = (
        "type",
        "scan_id",
        "state",
        "state_message",
        "last_state_check",
        "last_state_change",
        "metadata",
        "retrieved_scan_report",
        "retrieved_scan_report_technical",
        "subject_urls",
    )
    # todo: subject_urls inline

    readonly_fields = ["subject_urls", "metadata", "retrieved_scan_report", "retrieved_scan_report_technical"]

    @staticmethod
    def domains(obj):
        return "?"
        # this is usually 500 or whatever the setting is, which is a waste of resources...
        # obj.subject_urls.count()

    @staticmethod
    def online(obj):
        from constance import config

        return mark_safe(  # nosec not the best way to render html in the admin, but one that's in full admin control
            f"<a href='{config.INTERNET_NL_API_USERNAME}:{config.INTERNET_NL_API_PASSWORD}"
            f"@{config.INTERNET_NL_API_URL}/requests/{obj.scan_id}' target='_blank'>online</a>"
        )

    actions = []

    def attempt_rollback(self, request, queryset):
        for scan in queryset:
            recover_and_retry.apply_async([scan.pk])
        self.message_user(request, "Rolling back asynchronously. May take a while.")

    attempt_rollback.short_description = "Attempt rollback (async)"
    actions.append("attempt_rollback")

    def progress_scan(self, request, queryset):
        for scan in queryset:
            tasks = progress_running_scan(scan.pk)
            tasks.apply_async()
        self.message_user(request, "Attempting to progress scans (async).")

    progress_scan.short_description = "Progress scan (async)"
    actions.append("progress_scan")

    def force_finish(self, request, queryset):
        for scan in queryset:
            scan.state = "finished"
            scan.save()
        self.message_user(request, "Force finish.")

    force_finish.short_description = "Force finish"
    actions.append("force_finish")

    def force_request(self, request, queryset):
        for scan in queryset:
            scan.state = "requested"
            scan.save()
        self.message_user(request, "Force request.")

    force_request.short_description = "Force request"
    actions.append("force_request")


@admin.register(models.InternetNLV2StateLog)
class InternetNLV2StateLogAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("pk", "scan", "state", "state_message", "last_state_check", "at_when")
    search_fields = ("scan__scan_id",)
    list_filter = ("state", "state_message", "last_state_check", "at_when")
    fields = ("scan", "state", "state_message", "last_state_check", "at_when")


@admin.register(models.ScanProxy)
class ScanProxyAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = (
        "id",
        "protocol",
        "address",
        "check_result",
        "check_result_date",
        "currently_used_in_tls_qualys_scan",
        "last_claim_at",
        "manually_disabled",
        "is_dead",
        "request_speed_in_ms",
        "qualys_capacity_current",
        "qualys_capacity_max",
        "qualys_capacity_this_client",
    )
    search_fields = ("address",)
    list_filter = (
        "protocol",
        "is_dead",
        "is_dead_since",
        "check_result",
        "manually_disabled",
        "qualys_capacity_current",
    )
    fields = (
        "protocol",
        "address",
        "currently_used_in_tls_qualys_scan",
        "is_dead",
        "is_dead_since",
        "is_dead_reason",
        "manually_disabled",
        "check_result",
        "check_result_date",
        "request_speed_in_ms",
        "qualys_capacity_current",
        "qualys_capacity_max",
        "qualys_capacity_this_client",
        "last_claim_at",
    )

    actions = []

    def check_qualys_proxy(self, request, queryset):
        for proxy in queryset:
            check_proxy.apply_async([proxy.as_dict()])
        self.message_user(request, "Proxing checked asynchronously. May take some time before results come in.")

    check_qualys_proxy.short_description = "Check proxy"
    actions.append("check_qualys_proxy")

    def release_proxy(self, request, queryset):
        for proxy in queryset:
            proxy.out_of_resource_counter = 0
            proxy.currently_used_in_tls_qualys_scan = False
            proxy.save()

        self.message_user(request, "Proxies released.")

    release_proxy.short_description = "Release proxy"
    actions.append("release_proxy")

    def reset_proxy(self, request, queryset):
        for proxy in queryset:
            proxy.is_dead = False
            proxy.out_of_resource_counter = 0
            proxy.currently_used_in_tls_qualys_scan = False
            proxy.save()

        self.message_user(request, "Proxies reset.")

    reset_proxy.short_description = "Reset proxy"
    actions.append("reset_proxy")

    def disable_proxy(self, request, queryset):
        for proxy in queryset:
            proxy.manually_disabled = True
            proxy.save()

        self.message_user(request, "Proxies disabled.")

    disable_proxy.short_description = "Disable proxy"
    actions.append("disable_proxy")

    def enable_proxy(self, request, queryset):
        for proxy in queryset:
            proxy.manually_disabled = False
            proxy.save()

        self.message_user(request, "Proxies enabled.")

    enable_proxy.short_description = "Enable proxy"
    actions.append("enable_proxy")


@admin.register(models.PlannedScan)
class PlannedScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = (
        "id",
        "url",
        "activity",
        "scanner",
        "state",
        "last_state_change_at",
        "requested_at_when",
        "finished_at_when",
        "origin",
    )
    search_fields = ("url__url",)
    list_filter = ["activity", "scanner", "state", "last_state_change_at", "requested_at_when", "finished_at_when"][
        ::-1
    ]

    # url makes the edit page slow as it is not loaded async.
    readonly_fields = ["url"]

    fields = (
        "url",
        "activity",
        "scanner",
        "state",
        "last_state_change_at",
        "requested_at_when",
        "finished_at_when",
        "origin",
    )

    actions = []

    def set_state_requested(self, request, queryset):
        for plannedscan in queryset:
            plannedscan.state = State.requested.value
            plannedscan.save()
        self.message_user(request, "Set to requested.")

    set_state_requested.short_description = "Set to Requested"
    actions.append("set_state_requested")

    def set_state_finished(self, request, queryset):
        for plannedscan in queryset:
            plannedscan.state = State.finished.value
            plannedscan.save()
        self.message_user(request, "Set to finished.")

    set_state_finished.short_description = "Set to Finished"
    actions.append("set_state_finished")


@admin.register(models.PlannedScanLog)
class PlannedScanLogAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_filter = ["at_when"]
    list_display = ["id", "at_when", "line"]
    fields = ["id", "at_when", "line"]
    readonly_fields = ["id", "at_when", "line"]


@admin.register(models.PlannedScanStatistic)
class PlannedScanStatisticAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("at_when", "data")
    list_filter = ["at_when"][::-1]
    fields = ("at_when", "data")


@admin.register(models.Scanner)
class ScannerAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    help_text = "test"
    list_display = (
        "id",
        "name",
        "python_name",
        "enabled",
        "rate_limit",
        "description",
        "to",
        "needs_results_from",
        "enabled_acts",
    )
    save_as = True

    def enabled_acts(self, obj):
        return ", ".join([act.name for act in obj.enabled_activities.all()])

    actions = []

    def enable(self, request, queryset):
        for instance in queryset:
            instance.enabled = True
            instance.save()
        self.message_user(request, f"{queryset.count()} items enabled.")

    enable.short_description = "Enable"
    actions.append("enable")

    def disable(self, request, queryset):
        for instance in queryset:
            instance.enabled = False
            instance.save()
        self.message_user(request, f"{queryset.count()} items disabled.")

    disable.short_description = "Disable"
    actions.append("disable")


@admin.register(models.ScanType)
class ScanTypeAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = (
        "display_order",
        "id",
        "name",
        "include_in_report",
        "show_in_frontend",
        "description",
        "category2",
        "documentation_links2",
        "second_opinion_links2",
    )
    save_as = True
    list_per_page = 400
    actions = ordering_actions()

    def enable_show_in_frontend(self, request, queryset):
        for instance in queryset:
            instance.show_in_frontend = True
            instance.save()
        self.message_user(request, f"{queryset.count()} items enabled in frontend.")

    enable_show_in_frontend.short_description = "Show in Frontend"
    actions.append("enable_show_in_frontend")

    def disable_show_in_frontend(self, request, queryset):
        for instance in queryset:
            instance.show_in_frontend = False
            instance.save()
        self.message_user(request, f"{queryset.count()} items disabled in frontend.")

    disable_show_in_frontend.short_description = "Hidden in Frontend"
    actions.append("disable_show_in_frontend")

    def enable_include_in_report(self, request, queryset):
        for instance in queryset:
            instance.include_in_report = True
            instance.save()
        self.message_user(request, f"{queryset.count()} included in report.")

    enable_include_in_report.short_description = "Include in report"
    actions.append("enable_include_in_report")

    def disable_include_in_report(self, request, queryset):
        for instance in queryset:
            instance.include_in_report = False
            instance.save()
        self.message_user(request, f"{queryset.count()} excluded from report.")

    disable_include_in_report.short_description = "Excluded from report"
    actions.append("disable_include_in_report")

    def category2(self, obj):
        return [tag.name for tag in obj.category.all()]

    def documentation_links2(self, obj):
        return [tag.provider for tag in obj.documentation_links.all()]

    def second_opinion_links2(self, obj):
        return [tag.provider for tag in obj.second_opinion_links.all()]

    def save_model(self, request, obj, form, change):
        # allows to place a new item at the right position, moving certain items up.
        # if the display_order is zero, autoplace the item.

        if obj.display_order:
            super().save_model(request, obj, form, change)

        else:
            item_exists = models.ScanType.objects.all().filter(name=obj.name).order_by("-display_order").first()

            if item_exists:
                # if there is something form this item, place it where it belongs and move the rest +=1
                new_number = item_exists.display_order + 1

                moveup = models.ScanType.objects.all().filter(display_order__gte=new_number).order_by("-display_order")
                for config in moveup:
                    config.display_order += 1
                    config.save()

                obj.display_order = item_exists.display_order + 1
                super().save_model(request, obj, form, change)

            else:
                # if there is nothing from this item, then add it at the end.
                tmp = models.ScanType.objects.all().order_by("-display_order").first()

                if tmp:
                    obj.display_order = tmp.display_order + 1
                else:
                    obj.display_order = 1

                super().save_model(request, obj, form, change)


@admin.register(models.ScanTypeSecondOpinionLink)
class ScanTypeSecondOpinionLinkAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("provider", "friendly_name", "url")


@admin.register(models.ScanTypeDocumentationLink)
class ScanTypeScanTypeDocumentationLink(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("provider", "friendly_name", "url")
    ...


@admin.register(models.ScanTypeCategory)
class ScanTypeCategoryAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    ...


@admin.register(models.ScannerActivity)
class ScannerActivityAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    ...


@admin.register(models.FollowUpScan)
class FollowUpScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("id", "relevant_policies", "follow_up_scanner")

    def relevant_policies(self, obj):
        return "\n".join(
            [
                f"{p.summary_text_and_emoji()} - {p.scan_type} - " f"{p.conclusion}"
                for p in obj.run_follow_up_on_any_of_these_policies.all()
            ]
        )


@admin.register(models.Product)
class ProductAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("tags")

    search_fields = ("name", "vendor__name")
    list_display = (
        "id",
        "name",
        "is_irrelevant",
        "cve_details_link",
        "in_findings",
        "relations",
        # metadata
        "is_open_source",
        "common_execution_environment",
        "tag_list",
        "vendor",
        "goal",
        "impact",
    )

    @staticmethod
    def impact(obj):
        return f"T: {obj.technology_presence_security_impact} P:{obj.login_panel_presence_security_impact}"

    def tag_list(self, obj):
        return ", ".join(o.name for o in obj.tags.all())

    @staticmethod
    def in_findings(obj):
        return obj.scanner_finding_name_mapping.all().count()

    def relations(self, obj):
        return list(ProductHierarchy.objects.all().filter(product=obj))


@admin.register(models.ProductVendor)
class ProductVendorAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    search_fields = ("name",)

    list_display = ("id", "name", "uses")

    @staticmethod
    def uses(obj):
        return Product.objects.all().filter(vendor=obj).count()


@admin.register(models.ProductRelationship)
class ProductRelationshipAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    search_fields = ("name",)

    list_display = ("id", "name", "uses")

    @staticmethod
    def uses(obj):
        return ProductHierarchy.objects.all().filter(relationship=obj).count()


@admin.register(models.CookiePurpose)
class CookiePurposeAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("id", "name")

    def __str__(self):
        return self.name


@admin.register(models.ProductCookieIndicator)
class ProductCookieIndicatorAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("product", "product__vendor")

    list_display = ("id", "match_name", "match_domain", "match_path", "product", "most_significant_purpose", "link")
    exclude = ("match_regex", "match_field")

    search_fields = ("match_name", "product__vendor__name", "product__name")

    list_filter = ("most_significant_purpose", "product")

    @staticmethod
    def link(obj):
        if not obj.cookiedatabase_link:
            return ""
        return mark_safe(f"<a href='{obj.cookiedatabase_link}' target='_blank'>cdb</a>")

    @staticmethod
    def purpose(obj):
        return ", ".join(p.name for p in obj.purposes.all())

    @staticmethod
    def uses(obj):
        return ProductCookieIndicator.objects.all().filter(relationship=obj).count()


@admin.register(models.ProductGoal)
class ProductGoalAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    search_fields = ("name",)

    list_display = ("id", "name", "uses")

    @staticmethod
    def uses(obj):
        return Product.objects.all().filter(goal=obj).count()


@admin.register(models.ProductHierarchy)
class ProductHierarchyAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    search_fields = ("product__name", "related_product__name", "relationship__name")

    list_display = ("id", "product", "relationship", "related_product")


@admin.register(models.ScannerFinding)
class ScannerFindingAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("id", "name", "uses", "add_product", "products")

    @staticmethod
    def uses(obj):
        return Product.objects.all().filter(scanner_finding_name_mapping=obj).count()

    @staticmethod
    def add_product(obj):
        return mark_safe("<a href='/admin/scanners/product/add/'>add</a>")

    @staticmethod
    def products(obj):
        return list(Product.objects.all().filter(scanner_finding_name_mapping=obj))


# Workaround to import and export tags without too much hassle.
class TagProxy(taggit.models.Tag):
    class Meta:
        proxy = True


@admin.register(TagProxy)
class TagAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("id", "name", "slug")


@admin.register(models.HttpEndpointContent)
class HttpEndpointContentAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = (
        "id",
        "endpoint",
        "path",
        "title",
        "content_type",
        "status_code",
        "length_in_bytes",
        "at_when",
        "last_scan_moment",
        "is_the_latest",
    )

    list_filter = [
        "content_type",
        "at_when",
        "is_the_latest",
        "endpoint__protocol",
        "endpoint__port",
        "endpoint__ip_version",
    ][::-1]

    search_fields = ("endpoint__url__url", "content")


@admin.register(models.DomainIp)
class DomainIpAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("id", "domain", "ip_address", "ip_version", "at_when", "last_scan_moment", "is_the_latest")
    search_fields = ["domain", "ip_address"]
    list_filter = [
        "ip_address",
        "at_when",
        "is_the_latest",
        "ip_version",
    ][::-1]


@admin.register(models.GeoIp)
class GeoIpAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ip_address",
        "designation",
        "error",
        "continent_code",
        "country_iso_code_",
        "country_isp_iso_code_",
        "city_in_en",
        "as_number",
        "network",
        "as_organization",
        "isp_name",
        "at_when",
        "last_scan_moment",
        "is_the_latest",
    )

    search_fields = ["ip_address", "as_organization", "isp_name", "city_in_en", "network", "as_number"]

    list_filter = [
        "designation",
        "continent_code",
        "country_iso_code",
        "country_isp_iso_code",
        "city_in_en",
        "network",
        "as_number",
        "as_organization",
        "isp_name",
        "at_when",
        "is_the_latest",
    ][::-1]

    @staticmethod
    def country_iso_code_(obj):
        return nice_country(obj.country_iso_code)

    @staticmethod
    def country_isp_iso_code_(obj):
        return nice_country(obj.country_isp_iso_code)


def nice_country(country_code):
    if country_code:
        return f"{country_code}: {dict(countries)[country_code]}"
    return "-"


@admin.register(models.DomainMX)
class DomainMXAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("id", "domain", "mail_server_records", "last_scan_moment", "is_the_latest")


@admin.register(models.GeoIpCorrection)
class GeoIpCorrectionAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("id", "source", "link", "network", "country_code", "at_when", "last_scan_moment", "is_the_latest")
    list_filter = ["country_code", "at_when", "is_the_latest", "source"]
    search_fields = ["network", "country_code", "source"]

    def link(self, instance):
        if instance.source == "ripe":
            return mark_safe(
                f'<a href="https://rest.db.ripe.net/search.json?query-'
                f"string={instance.network}&type-filter=inetnum,inet6num"
                f'&flags=no-referenced&flags=no-irt&source=RIPE"'
                f'target="_blank">{instance.network}</a>'
            )
        return ""

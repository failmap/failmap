from datetime import datetime, timedelta, timezone
from typing import List

from django.db import models
from django.forms import model_to_dict
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from jsonfield import JSONField
from taggit.managers import TaggableManager

from websecmap.organizations.models import Url
from websecmap.reporting.models import ScanPolicy


class SecurityPolicy(models.Model):
    name = models.CharField(max_length=255)
    technical_policy_name = models.SlugField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True)

    # for automatically determining default policies per endpoint
    common_subdomains = JSONField(
        blank=True, help_text="List[str] of common subdomains where this policy applies to", default=[]
    )
    common_ports = JSONField(blank=True, help_text="List[int] of port numbers this policy applies to", default=[])
    common_protocols = JSONField(blank=True, help_text="List[str] of protocols this policy applies to", default=[])
    common_ip_versions = models.IntegerField(
        blank=True, null=True, help_text="0 for all, 4 for ipv4, 6 for ipv6", default=0
    )

    affect_explain_scoring_policy = models.ManyToManyField(
        ScanPolicy,
        blank=True,
        help_text="Will explain specific scan scores on this endpoint so they are not counted as issues anymore. "
        "It makes sense to only explain scan scores that have a negative impact. And be sure that this "
        "score is actually applied to the previous set of critera / these specific endpoints.",
    )


class Endpoint(models.Model):
    """
    Endpoints are created using (some) scan tools but mostly harvesters.

    An endpoint is anything that exposes to the internet that can be scanned.
    It can have any protocol, also non-usual protocols. This is where it gets fuzzy.
    But there are some conventions that mediocrely implemented.

    There can be a lot of endpoints for a domain.

    example.com might result in:
    protocols: http, https, telnet
    ports: 21, 80, 443 (do expect non-standard, hidden, ports)
    ip: multiple ipv4 and ipvquit6 addresses

    There can be unlimited ip's * 65535 ports * dozens of protocol endpoints per domain.

    What's the difference between an URL and an endpoint?
    A URL is a point of investigation. We know it exists, but we don't know anything about it:
    - we don't know it's services. Maybe therefore an Endpoint should be called a service.
        but that is not really common.
    Additionally it's easier for humans to understand a "url", much more than that there are
    ports, protocols, ip-addresses and more of that.
    """

    # imported using a string, to avoid circular imports, which happens in complexer models
    # https://stackoverflow.com/questions/4379042/django-circular-model-import-issue
    url = models.ForeignKey(Url, null=True, blank=True, on_delete=models.CASCADE)

    ip_version = models.IntegerField(
        help_text="Either 4: IPv4 or 6: IPv6. There are basically two possibilities to reach the endpoint, "
        "which due to immaturity often look very different. The old way is using IPv4"
        "addresses (4) and the newer method is uing IPv6 (6). The internet looks a whole lot"
        "different between IPv4 or IPv6. That shouldn't be the case, but it is.",
        default=4,
    )

    port = models.IntegerField(
        default=443,
        help_text="Ports range from 1 to 65535.",
        db_index=True,  # mainly to speeed up the admin interface
    )  # 1 to 65535

    protocol = models.CharField(
        max_length=20,
        help_text="Lowercase. Mostly application layer protocols, such as HTTP, FTP,"
        "SSH and so on. For more, read here: "
        "https://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol",
        db_index=True,  # mainly to speeed up the admin interface
    )

    discovered_on = models.DateTimeField(blank=True, null=True)

    # Till when the endpoint existed and why it was deleted (or didn't exist at all).
    is_dead = models.BooleanField(
        default=False,
        help_text="Use the 'declare dead' button to autofill the date. "
        "If the port is closed, or the endpoint is otherwise"
        "not reachable over the specified protocol, then mark"
        "it as dead. A scanner for this port/protocol can also"
        "declare it dead. This port is closed on this protocol."
        "",
    )

    is_dead_since = models.DateTimeField(blank=True, null=True)

    is_dead_reason = models.CharField(max_length=255, blank=True, null=True)

    origin = models.CharField(max_length=255, blank=True, null=True)

    security_policies = models.ManyToManyField(
        SecurityPolicy,
        blank=True,
    )

    @property
    def security_policies_list(self) -> List[str]:
        return list(self.security_policies.values_list("technical_policy_name", flat=True))

    def __str__(self):
        if self.is_dead:
            return f"✝ IPv{self.ip_version} {self.protocol}/{self.port} | [{self.id}] {self.url} "

        return f"IPv{self.ip_version} {self.protocol}/{self.port} | [{self.id}] {self.url} "

    def uri_url(self):
        # dns_a_aaaa is an ipv6 A/AAAA record, which might lead to a webserver. Assuming that webserver
        # is available over https (as that should be the standard). It might not be reachable.
        protocol = "https" if self.protocol == "dns_a_aaaa" else self.protocol

        # dns_a_aaaa does not have a port as it's not on http level, it has port set to 0.
        if self.port:
            return f"{protocol}://{self.url.url}:{self.port}"

        return f"{protocol}://{self.url.url}"

    def host(self):
        return self.url.url

    # when testing for ipv4 or ipv6, an endpoint is mutually exclusive.
    def is_ipv4(self):
        return self.ip_version == 4

    def is_ipv6(self):
        return self.ip_version == 6

    @staticmethod
    # while being extermely slow, it sort of works... It's better than waiting for the whole list to download.
    # jet only feature: http://jet.readthedocs.io/en/latest/autocomplete.html
    def autocomplete_search_fields():
        return ("url__url",)

    class Meta:
        verbose_name = _("endpoint")
        verbose_name_plural = _("endpoint")


class ScanProxy(models.Model):
    """
    A transparent proxy sends your real IP address in the HTTP_X_FORWARDED_FOR header,
    this means a website that does not only determine your REMOTE_ADDR but also check for specific proxy headers
    will still know your real IP address. The HTTP_VIA header is also sent, revealing that you are using a proxy server.

    An anonymous proxy does not send your real IP address in the HTTP_X_FORWARDED_FOR header, instead it submits the IP
    address of the proxy or is just blank. The HTTP_VIA header is sent like with a transparent proxy, also revealing
    that you are using a proxy server.

    An elite proxy only sends REMOTE_ADDR header, the other headers are blank/empty, hence making you seem like a
    regular internet user who is not using a proxy at all.
    """

    # todo: do we have to support socks proxies? It's possible and allows name resolution.

    protocol = models.CharField(
        max_length=10, help_text="Whether to see this as a http or https proxy", default="https"
    )

    address = models.CharField(
        max_length=255,
        help_text="An internet address, including the http/https scheme. Works only on IP. Username / pass can be"
        "added in the address. For example: https://username:password@192.168.1.1:1337/",
    )

    currently_used_in_tls_qualys_scan = models.BooleanField(
        default=False,
        help_text="Set's the proxy as in use, so that another scanner knows that this proxy is being used at this "
        "moment. After a scan is completed, the flag has to be disabled. This of course goes wrong with "
        "crashes. So once in a while, if things fail or whatever, this might have to be resetted.",
    )

    is_dead = models.BooleanField(
        default=False,
        help_text="Use the 'declare dead' button to autofill the date. "
        "If the port is closed, or the endpoint is otherwise"
        "not reachable over the specified protocol, then mark"
        "it as dead. A scanner for this port/protocol can also"
        "declare it dead. This port is closed on this protocol."
        "",
    )

    manually_disabled = models.BooleanField(default=False, help_text="Proxy will not be used if manually disabled.")

    is_dead_since = models.DateTimeField(blank=True, null=True)

    is_dead_reason = models.CharField(max_length=255, blank=True, null=True)

    check_result = models.CharField(
        max_length=60, help_text="The result of the latest 'check proxy' call.", default="Unchecked."
    )

    check_result_date = models.DateTimeField(blank=True, null=True)

    last_claim_at = models.DateTimeField(blank=True, null=True)

    request_speed_in_ms = models.IntegerField(
        default=-1,
    )

    qualys_capacity_current = models.IntegerField(
        default=-1,
    )

    qualys_capacity_max = models.IntegerField(
        default=-1,
    )

    qualys_capacity_this_client = models.IntegerField(
        default=-1,
    )

    out_of_resource_counter = models.IntegerField(
        default=0,
        help_text="Every time the proxy has not enough resources, this number will increase with one. A too high "
        "number makes it easy not to use this proxy anymore.",
    )

    def as_dict(self):
        return {
            "id": self.pk,
            "protocol": self.protocol,
            "address": self.address,
        }

    @staticmethod
    def add_address(address):
        if not ScanProxy.objects.all().filter(address=address).exists():
            proxy = ScanProxy()
            proxy.address = address
            proxy.protocol = "https"
            proxy.save()

    def __str__(self):
        if self.is_dead:
            return f"✝ {self.pk} {self.address}"

        return f"{self.pk} {self.address}"


class UrlIp(models.Model):
    """
    IP addresses of endpoints change constantly. They are more like metadata. The IP metadata can
    be a source of endpoints or other organization specific things. Therefore we save it.
    We now also have the room to do reverse DNS on these IP addresses.

    At one time an endpoint can have multiple IPv4 and IPv6 addresses. They are not worth too much
    and managed quite brutally by scanners (some just deleting all of the existing ones if there is
    a new set of addresses, which is common for some service providers).

    If an IP address does indeed have a website, or other service specifically, it should be treated
    as URL, as the chance is very high this URL is as static as any other URL.

    It's perfectly possible to make this a many-many relation to save some data. But that might be
    done in the next version as it increases complexity slightly.
    """

    url = models.ForeignKey(Url, blank=True, null=True, on_delete=models.CASCADE)

    ip = models.CharField(
        max_length=255,
        help_text="IPv4 or IPv6 Address. Addresses have to be normalized to the compressed "
        "representation: removing as many zeros as possible. For example:  "
        "IPv6: abcd:0000:0000:00fd becomes abcd::fd, or "
        "IPv4: 127.000.000.001 = 127.0.0.1",
    )

    is_v4 = models.BooleanField(default=True)

    rdns_name = models.CharField(
        max_length=255,
        help_text="The reverse name can be a server name, containing a provider or anything else."
        "It might contain the name of a yet undiscovered url or hint to a service.",
        blank=True,
    )

    discovered_on = models.DateTimeField(blank=True, null=True)

    is_unused = models.BooleanField(
        default=False,
        help_text="If the address was used in the past, but not anymore."
        "It's possible that the same address is more than once "
        "associated with and endpoint over time, as some providers"
        "rotate a set of IP addresses.",
    )

    is_unused_since = models.DateTimeField(blank=True, null=True)

    is_unused_reason = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        if self.discovered_on:
            return f"{self.ip} {self.discovered_on.date()}"

        return f"{self.ip} @???"

    class Meta:
        verbose_name = _("urlip")
        verbose_name_plural = _("urlip")


def one_year_in_the_future():
    return datetime.now(timezone.utc) + timedelta(days=365)


class LatestScanMixin(models.Model):
    """
    This contains a boolean field that notes if this was the latest scan for this url/endpoint.

    This is needed to make sure scanners can easily filter on the latest result on a certain url. There is no
    django ORM construct for this. The latest is automatically maintained by the nonsense, which will both
    set new scans as being the latest while unsetting all previous scans to not be the latest.

    url:          date:     value:  latest:
    example.com   1 april   F       False
    example.com   2 april   B       False
    example.com   3 april   A       True
    ... etc
    """

    is_the_latest_scan = models.BooleanField(
        default=False,
        help_text="Notes if this was the latest scan for this url/endpoint. Scanmanagers set this value.",
    )

    class Meta:
        abstract = True


class ExplainMixin(models.Model):
    """
    An explanation excludes the grading to impact the report. The result is added in the report,
    strikethrough, with an explanation and the expiry time of this explanation.

    Explains are available for all scans: GenericUrlScan, GenericEndpointScan this means
    and extra model for each of these scans types.

    Given there is a 1-1 relation, the info is saved in scans. This reserves about 1kb per scan, which is somewhat
    acceptable.

    Todo: also create the correct permissions for someone to explain a thing.
    """

    comply_or_explain_is_explained = models.BooleanField(
        default=False,
        help_text="Shorthand to indicate that something is explained. Only when this field is set to True, the "
        "explanation is ",
        verbose_name="is explained",
    )

    comply_or_explain_explanation_valid_until = models.DateTimeField(
        help_text="Set to one year in the future. "
        "Will expire automatically after a scan finds a change on this service. "
        "As long as the rating stays the same, the finding is explained and the issue ignored.",
        verbose_name="explanation valid until",
        null=True,
        blank=True,
    )

    comply_or_explain_explanation = models.CharField(
        max_length=1000,
        help_text="Text that helps explain why this result is not counted in the report. For example: "
        "a broken scanner or another edge-case that is mainly on the side of the scanning party.",
        verbose_name="explanation",
        default="",
        null=True,
        blank=True,
    )

    comply_or_explain_explained_by = models.CharField(
        max_length=512,
        help_text="Please also refer to a thread, discussion or another fact that can be verified.",
        verbose_name="explained by",
        default="",
        null=True,
        blank=True,
    )

    comply_or_explain_explained_on = models.DateTimeField(
        help_text="From this moment the rating will be muted.", verbose_name="explained on", null=True, blank=True
    )

    comply_or_explain_case_handled_by = models.CharField(
        max_length=512,
        help_text="Who entered the comply-or-explain information, so it's easy to find the right person to talk to in "
        "case of follow-ups.",
        verbose_name="case handled by",
        default="",
        null=True,
        blank=True,
    )

    comply_or_explain_case_additional_notes = models.CharField(
        max_length=1000,
        help_text="Notes about the scenario for follow up. Things such as phone numbers, mail addresses, contact info."
        "Will not be exported, but are not secret.",
        verbose_name="additional case notes",
        default="",
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True


class PlannedScanStatistic(models.Model):
    at_when = models.DateTimeField()
    data = JSONField()


class Activity(models.IntegerChoices):
    # can't switch case anymore. And its also ugly.
    unknown = 0, "unknown"  # pylint: disable=invalid-name
    discover = 1, "discover"  # pylint: disable=invalid-name
    verify = 2, "verify"  # pylint: disable=invalid-name
    scan = 3, "scan"  # pylint: disable=invalid-name


class State(models.IntegerChoices):
    unknown = 0, "unknown"  # pylint: disable=invalid-name
    requested = 1, "requested"  # pylint: disable=invalid-name
    picked_up = 2, "picked_up"  # pylint: disable=invalid-name
    finished = 3, "finished"  # pylint: disable=invalid-name
    error = 4, "error"  # pylint: disable=invalid-name
    timeout = 5, "timeout"  # pylint: disable=invalid-name


# https://docs.djangoproject.com/en/dev/topics/db/models/#id6
class GenericScanMixin(ExplainMixin, LatestScanMixin):
    """
    This is a fact, a point in time.
    """

    type = models.CharField(
        max_length=60,
        db_index=True,
        help_text="The type of scan that was performed. Instead of having different tables for each"
        "scan, this label separates the scans.",
    )
    rating = models.CharField(
        max_length=128,
        default=0,
        help_text="Preferably an integer, 'True' or 'False'. Keep ratings over time consistent.",
        db_index=True,  # mainly needed for responsive admin interface
    )
    explanation = models.CharField(
        max_length=255,
        default=0,
        help_text="Short explanation from the scanner on how the rating came to be.",
        blank=True,
    )
    evidence = models.CharField(
        max_length=9001,
        default=0,
        help_text="Content that might help understanding the result.",
        blank=True,
    )
    last_scan_moment = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="This gets updated when all the other fields stay the same. If one changes, a"
        "new scan will be saved, obsoleting the older ones.",
    )
    rating_determined_on = models.DateTimeField(
        help_text="This is when the current rating was first discovered. It may be obsoleted by"
        "another rating or explanation (which might have the same rating). This date "
        "cannot change once it's set.",
        db_index=True,  # mainly needed for responsive admin interface
    )

    class Meta:
        """
        From the docs:

        Django does make one adjustment to the Meta class of an abstract base class: before installing the Meta
        attribute, it sets abstract=False. This means that children of abstract base classes don’t automatically
        become abstract classes themselves. Of course, you can make an abstract base class that inherits from
        another abstract base class. You just need to remember to explicitly set abstract=True each time.
        """

        abstract = True
        ordering = [
            "-rating_determined_on",
        ]


class EndpointGenericScan(GenericScanMixin):
    """
    Only changes are saved as a scan.
    """

    endpoint = models.ForeignKey(
        Endpoint,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.rating_determined_on.date()}: {self.type} {self.rating} on {self.endpoint}"


class UrlGenericScan(GenericScanMixin):
    """
    Only changes are saved as a scan.
    """

    url = models.ForeignKey(Url, null=True, blank=True, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.rating_determined_on.date()}: {self.type} {self.rating} on {self.url}"


class EndpointGenericScanScratchpad(models.Model):
    """
    A debugging channel for generic scans.
    You can easily truncate this log after 30 days.
    """

    type = models.CharField(
        max_length=60,
        db_index=True,
        help_text="The type of scan that was performed. Instead of having different tables for each"
        "scan, this label separates the scans.",
    )
    domain = models.CharField(
        max_length=255, help_text="Deprecated. Used when there is no known Endpoint.", blank=True, null=True
    )
    at_when = models.DateTimeField(auto_now_add=True)
    data = models.TextField(help_text="Whatever data to dump for debugging purposes.")


class Screenshot(models.Model):
    endpoint = models.ForeignKey(Endpoint, null=True, blank=True, on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    image = models.ImageField(
        upload_to="screenshots/", height_field="height_pixels", width_field="width_pixels", default=None, null=True
    )
    width_pixels = models.IntegerField(default=0)
    height_pixels = models.IntegerField(default=0)
    created_on = models.DateTimeField(auto_now_add=True, db_index=True)


class InternetNLV2Scan(models.Model):
    """

    Version 2 of the Internet.nl API is implemented here.

    """

    type = models.CharField(max_length=30, help_text="mail, mail_dashboard or web", blank=True, null=True)

    scan_id = models.CharField(
        max_length=32,
        help_text="The scan ID that is used to request status and report information.",
        blank=True,
        null=True,
    )

    # registered, scanning, finished
    state = models.CharField(
        max_length=200,
        help_text="where the scan is: registered, scanning, creating_report, finished, failed",
        blank=True,
        null=True,
    )

    state_message = models.CharField(
        max_length=200, help_text="Information about the status, for example error information.", blank=True, null=True
    )

    last_state_check = models.DateTimeField(blank=True, null=True)

    last_state_change = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When this state changed the last time, so no in-between updates about the state.",
    )

    # metadata returned from the scan, contains info about the api version, tracking info, scan type etc.
    metadata = JSONField(default=None, blank=True, null=True)

    # this allows filtering during the creation of a scan.
    # todo: what if a url is deleted, this relation should also be deleted, is that happening?
    subject_urls = models.ManyToManyField(Url)

    # for error recovery and debugging reasons, store the entire result (which can be pretty huge).
    retrieved_scan_report = JSONField(default=None, blank=True, null=True)

    created_at_when = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.pk}: {self.scan_id} {self.state}"


class InternetNLV2StateLog(models.Model):
    scan = models.ForeignKey(
        InternetNLV2Scan,
        on_delete=models.CASCADE,
    )

    state = models.CharField(
        max_length=255, blank=True, default="", help_text="The state that was registered at a certain moment in time."
    )

    state_message = models.CharField(
        max_length=200, help_text="Information about the status, for example error information.", blank=True, null=True
    )

    last_state_check = models.DateTimeField(
        blank=True, null=True, help_text="Last time this state was written to this field, which can happen regularly."
    )

    at_when = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.scan.pk}.{self.pk}: {self.state}"


# A debugging table to help with API interactions.
# This can be auto truncated after a few days.
# Not anymore, since it's used to see if there are DNS problems (unresolvable domains)
# That should be factored out first.
class TlsQualysScratchpad(models.Model):
    """
    A debugging channel for all communications with Qualys.
    You can easily truncate this log after 30 days.
    """

    domain = models.CharField(max_length=255)
    at_when = models.DateTimeField(auto_now_add=True)
    data = models.TextField()


class ScanTypeSecondOpinionLink(models.Model):
    url = models.CharField(max_length=200, blank=True, null=True)
    provider = models.CharField(max_length=200, blank=True, null=True)
    friendly_name = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return f"{self.provider}"


class ScanTypeDocumentationLink(models.Model):
    url = models.CharField(max_length=200, blank=True, null=True)
    provider = models.CharField(max_length=200, blank=True, null=True)
    friendly_name = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return f"{self.provider}"


class ScanTypeCategory(models.Model):
    # used in the frontend. Things like:
    # integrity, confidentiality, availability, email, website, dns,
    name = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return f"{self.name}"


class ScanSubject(models.IntegerChoices):
    ENDPOINT = 0, "endpoint"
    URL = 1, "url"


class ScannerActivity(models.Model):
    # discover, verify, scan
    name = models.CharField(max_length=40, blank=True, null=True)

    def __str__(self):
        return f"{self.name}"


class ScanType(models.Model):
    name = models.CharField(max_length=200, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    second_opinion_links = models.ManyToManyField(to=ScanTypeSecondOpinionLink)
    documentation_links = models.ManyToManyField(to=ScanTypeDocumentationLink)
    category = models.ManyToManyField(to=ScanTypeCategory)
    include_in_report = models.BooleanField(
        default=False,
        help_text="When included into the report the value is also"
        " used when building statistics. It will be "
        "in the report that is on the front end, but "
        "might not be set to visible.",
    )
    show_in_frontend = models.BooleanField(
        default=False,
        help_text="Show this value in the front end, it might be "
        "included"
        "in the report but just not shown. Notice that "
        "things that are in the report do count towards "
        "statistics, so its unusual to disable this without"
        " also disabling report inclusion.",
    )
    display_order = models.PositiveIntegerField(
        _("order"),
        default=0,
        blank=False,
        null=False,
        help_text="Setting this to 0 will automatically set the country at a guessed position. For example: near the"
        "same country or at the end of the list.",
    )

    def __str__(self):
        return f"{self.name}"

    class Meta:
        # django-admin-sortable2
        ordering = ["display_order"]


class Scanner(models.Model):
    name = models.CharField(max_length=200, blank=True, null=True)

    # a scanner in the python code does NOT know what id it has. We can force id's, but then use names instead so its
    # easier to understand. Somewhere a translation needs to be made.
    python_name = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="The name as used in the python code. This is fragile so only change"
        " this when you know what you are doing.",
    )
    description = models.CharField(max_length=255, blank=True, null=True)
    to = models.PositiveSmallIntegerField(
        choices=ScanSubject.choices,
        default=ScanSubject.ENDPOINT,
        db_index=True,
    )
    plannable_activities = models.ManyToManyField(
        to=ScannerActivity, help_text="All possible activities this scanner" "can perform"
    )

    enabled = models.BooleanField(
        default=False,
        help_text="When the scanner is enabled with will performed the" "allowed activities listed below.",
    )
    enabled_activities = models.ManyToManyField(
        to=ScannerActivity,
        help_text="The activities this scanner is " "allowed to perform, which is a subset of" " plannable activities.",
        related_name="scanner_enabled_activities",
    )
    rate_limit = models.IntegerField(
        default=500,
        help_text="The maximum number of simultaneous tasks inside the "
        "queue. Tweak this setting to not overwhelm workers and "
        "gradually work through all planned tasks.",
    )

    # currently limited to one scanner. This might become something else in the future
    # usually the hierarchy should be stored externally, but the limit to one has served
    # well for years.
    # Removed db constraint in order to easily import data.
    needs_results_from = models.ForeignKey(
        "self", blank=True, on_delete=models.CASCADE, default="", null=True, db_constraint=False
    )

    # These are derivatives of the scantype
    # can_discover_endpoints = models.BooleanField()
    # can_verify_endpoints = models.BooleanField()
    # can_scan_endpoints = models.BooleanField()
    # can_discover_urls = models.BooleanField()
    # can_verify_urls = models.BooleanField()
    # can_scan_urls = models.BooleanField()
    # creates_url_scan_types ...
    # creates_endpoint_scan_types ...

    creates_scan_types = models.ManyToManyField(to=ScanType, blank=True)

    def __str__(self):
        return f"{self.name}"


class FollowUpScan(models.Model):
    # Used to schedule comply or explain scans after a certain scan has run. This means comply or explain
    # scanners can be performed on a more lax schedule. This just creates planned scans, it does not
    # build a more complex task with all kinds of extra subtasks from the other scanners: a scanner may not function
    # or may be buggy or whatever, which should not influence the tasks created. Comply or explain tasks are executed
    # pretty swiftly usually.
    run_follow_up_on_any_of_these_policies = models.ManyToManyField(
        ScanPolicy,
        blank=True,
        help_text="There are conditions here on when the follow up will be performed. This is a 'rough conclusion', "
        "which is used to auto-document when corrections are applied.",
        db_constraint=False,
    )

    follow_up_scanner = models.ForeignKey(Scanner, on_delete=models.CASCADE, db_constraint=False)

    def __str__(self):
        return f"First: ... Then: {self.follow_up_scanner.name}"


class PlannedScan(models.Model):
    """
    A planned scan is always performed per url, even if the scan itself is about endpoints. The endpoints can be
    retrieved at a later state,
    """

    url = models.ForeignKey(Url, on_delete=models.CASCADE)
    activity = models.PositiveSmallIntegerField(
        choices=Activity.choices, default=Activity.unknown, db_index=True, help_text="discover, verify or scan"
    )

    scanner = models.ForeignKey(Scanner, on_delete=models.CASCADE)

    state = models.PositiveSmallIntegerField(
        choices=State.choices,
        default=State.unknown,
        db_index=True,
    )

    """
        WHERE
        requested_at_when >= '%(when)s'
    """
    requested_at_when = models.DateTimeField(db_index=True)

    last_state_change_at = models.DateTimeField(
        null=True,
    )

    # some metadata where the scan is originating from, mainly to see follow-up scans
    origin = models.CharField(max_length=255, blank=True, null=True)

    finished_at_when = models.DateTimeField(null=True, help_text="when finished, timeout, error", blank=True)

    # add joined index over scanner, activity, state, so queries are faster:
    # see: https://docs.djangoproject.com/en/3.0/ref/models/options/#indexes
    class Meta:
        indexes = [models.Index(fields=["scanner", "activity", "state"])]


class PlannedScanError(models.Model):
    # since many plannedscans will run just fine, don't add this information to that model.

    planned_scan = models.ForeignKey(PlannedScan, on_delete=models.CASCADE)

    debug_information = models.CharField(max_length=512)


class PlannedScanLog(models.Model):
    # Logs all changes to planned scans, so you can see what has been picked up/finished and whatnot
    # This log is in plain text and meant for easy human consumption. It's not your referential record fest
    # It is meant to be a simple "what happened then" log, not one where you need to filter back on what scanner etc.

    # This also logs changes on scans that have not been requested, but that might have finished etc.
    at_when = models.DateTimeField(auto_now_add=True)
    line = models.CharField(max_length=255)


"""
phpMyAdmin is written in PHP, which runs on Windows/Linux/MacOS, has the goal of Database Management.
"""


class ScannerFinding(models.Model):
    name = models.CharField(max_length=200, blank=True, null=False)
    slug = models.SlugField(max_length=200, blank=True)
    nice_name = models.CharField(max_length=200, blank=True)
    scanner = models.ForeignKey(Scanner, on_delete=models.CASCADE, null=True, blank=True)

    def save(self, *args, **kwarg):
        self.slug = slugify(self.name)
        super().save(*args, **kwarg)

    def __str__(self):
        return self.name


class ProductGoal(models.Model):
    # Operating System, Data Storage, Programming Language, Web Framework, Log Management, E-Mail, Database Management,
    # Virtual Private Network, Telephony, Software Version Tracking, Web Shop, Online Collaboration, Online Meetings,
    # Monitoring, Authentication, Knowledge Base (wiki), Typesetting, Commenting, Mail Campaigns etc
    name = models.CharField(max_length=200, blank=True, null=False)
    slug = models.SlugField(max_length=200, blank=True)

    def save(self, *args, **kwarg):
        self.slug = slugify(self.name)
        super().save(*args, **kwarg)

    def __str__(self):
        return self.name


class ProductVendor(models.Model):
    name = models.CharField(max_length=200, blank=True, null=False)
    slug = models.SlugField(max_length=200, blank=True)

    def save(self, *args, **kwarg):
        self.slug = slugify(self.name)
        super().save(*args, **kwarg)

    def __str__(self):
        return self.name


class Product(models.Model):
    # Filled in by hand / a script
    name = models.CharField(max_length=200, blank=True, null=False)
    cve_details_link = models.CharField(max_length=200, blank=True, null=False)
    open_cve_link = models.CharField(max_length=200, blank=True, null=False)
    scanner_finding_name_mapping = models.ManyToManyField(to=ScannerFinding, blank=True)

    # Automatically filled in
    slug = models.SlugField(max_length=200, blank=True, null=False)
    vendor = models.ForeignKey(ProductVendor, blank=True, null=True, on_delete=models.CASCADE)
    goal = models.ForeignKey(ProductGoal, blank=True, null=True, on_delete=models.CASCADE)
    arbitrary_json_data = JSONField(blank=True, null=True)

    intended_use_case_description = models.CharField(max_length=600, blank=True, null=True)
    contextual_graph = models.CharField(max_length=2000, blank=True, null=True)
    tags = TaggableManager(blank=True)

    is_open_source = models.BooleanField(default=None, null=True, blank=True)

    # Server, Browser, Both (for javascript i guess), or Unknown
    common_execution_environment = models.CharField(max_length=20, blank=True, null=True)

    # products / technologies that should not be returned because they never add a lot of value
    # such as defaults and such.
    is_irrelevant = models.BooleanField(default=False, null=True, blank=True)

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "vendor": model_to_dict(self.vendor) if self.vendor else {},
            "cve_details_link": self.cve_details_link,
            "open_cve_link": self.open_cve_link,
            "is_open_source": self.is_open_source,
            "common_execution_context": self.common_execution_environment,
            "goal": self.goal.name if self.goal else "",
            "tags": list(self.tags.all().values_list("name", flat=True)),
            "intended_use_case_description": self.intended_use_case_description,
        }

    def save(self, *args, **kwarg):
        self.slug = slugify(self.name)
        super().save(*args, **kwarg)

    @property
    def verbose_name(self):
        summary = ""

        if self.vendor and self.vendor.name.lower() not in ["open source community", "unknown"]:
            summary += f"{self.vendor} "

        if self.name:
            summary += f"{self.name} "

        return summary.strip()

    def __str__(self):
        summary = ""
        if self.vendor:
            summary += f"{self.vendor} "

        if self.name:
            summary += f"'{self.name}' "

        if self.goal:
            summary += f" ({self.goal})"

        return summary.strip()


class ProductRelationship(models.Model):
    # 'written in', 'runs on', 'plugin', 'stores data in', just to make complete sentences.
    name = models.CharField(max_length=200, blank=True, null=False)
    slug = models.SlugField(max_length=200, blank=True)

    def save(self, *args, **kwarg):
        self.slug = slugify(self.name)
        super().save(*args, **kwarg)

    def __str__(self):
        return self.name


class PortalPublishingReason(models.Model):
    # backend_system, development_tool, sysadmin_tool, content_management_portal, remote_work
    name = models.SlugField(max_length=200)

    def __str__(self):
        return self.name


class ProductWithPortal(models.Model):
    """
    Some products have portals, these can be auto-filled here from scanner_finding_name_mapping.

    Some portals are fine to show online, some are not. This table holds that specific information.

    This table is separated from the normal product table as it's easy to mix up these fields with results
    from other tech scans such as: this open port is from MySQL. That has their own meaning and results.
    Also it's fine to have mySQL running (for example in xampp) but it should not be exposed.
    """

    # todo: this can be auto-filled from portal scans.
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    # fine for netscalers, work from home solutions? null = unknown.
    login_portal_should_be_public = models.BooleanField(default=False, null=True, blank=True)
    # backend_system, development_tool, sysadmin_tool, content_management_portal, remote_work. These fields
    # will have to be translated but its not clear which options will exist in the future. Therefore its not an
    # enum but a reference.
    reasoning_for_public_or_not = models.ForeignKey(PortalPublishingReason, on_delete=models.CASCADE)


class ProductHierarchy(models.Model):
    # Separate the hierarchy / network from the data itself, so it can be easily replaced / upgraded etc.
    # It's also not important how fast it is given it's a long duration cached read and virtually nothing
    # ever changes in the software world.
    # The N to 1 relationships are the most interesting.
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="product")
    related_product = models.ForeignKey(Product, on_delete=models.CASCADE, blank=True, related_name="related_to")
    relationship = models.ForeignKey(ProductRelationship, on_delete=models.CASCADE, blank=True)

    def __str__(self):
        return f"{self.product} -> {self.relationship} -> {self.related_product}"

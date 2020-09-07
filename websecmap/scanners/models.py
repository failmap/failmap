# coding=UTF-8
from datetime import datetime, timedelta

import pytz
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.translation import gettext_lazy as _
from jsonfield import JSONField

from websecmap.organizations.models import Url


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
    url = models.ForeignKey(
        Url,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    ip_version = models.IntegerField(
        help_text="Either 4: IPv4 or 6: IPv6. There are basically two possibilities to reach the endpoint, "
                  "which due to immaturity often look very different. The old way is using IPv4"
                  "addresses (4) and the newer method is uing IPv6 (6). The internet looks a whole lot"
                  "different between IPv4 or IPv6. That shouldn't be the case, but it is.",
        default=4
    )

    port = models.IntegerField(
        default=443,
        help_text="Ports range from 1 to 65535.")  # 1 to 65535

    protocol = models.CharField(
        max_length=20,
        help_text="Lowercase. Mostly application layer protocols, such as HTTP, FTP,"
                  "SSH and so on. For more, read here: "
                  "https://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol",
    )

    discovered_on = models.DateTimeField(
        blank=True,
        null=True
    )

    # Till when the endpoint existed and why it was deleted (or didn't exist at all).
    is_dead = models.BooleanField(
        default=False,
        help_text="Use the 'declare dead' button to autofill the date. "
                  "If the port is closed, or the endpoint is otherwise"
                  "not reachable over the specified protocol, then mark"
                  "it as dead. A scanner for this port/protocol can also"
                  "declare it dead. This port is closed on this protocol."
                  ""
    )

    is_dead_since = models.DateTimeField(
        blank=True,
        null=True
    )

    is_dead_reason = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    def __str__(self):
        if self.is_dead:
            return "✝ IPv%s %s/%s | [%s] %s  " % (self.ip_version, self.protocol, self.port, self.id, self.url)
        else:
            return "IPv%s %s/%s | [%s] %s " % (self.ip_version, self.protocol, self.port, self.id, self.url)

    def uri_url(self):
        return "%s://%s:%s" % (self.protocol, self.url.url, self.port)

    # when testing for ipv4 or ipv6, an endpoint is mutually exclusive.
    def is_ipv4(self):
        return self.ip_version == 4

    def is_ipv6(self):
        return self.ip_version == 6

    @staticmethod
    def force_get(url, ip_version, protocol, port):
        endpoints = Endpoint.objects.all().filter(
            protocol=protocol,
            url=url,
            port=port,
            ip_version=ip_version,
            is_dead=False).order_by('-discovered_on')

        count = endpoints.count()
        # >0: update the endpoint with the current information, always add to the newest one, even if there are dupes
        # 0: make new endpoint, representing the current result
        if count > 0:
            return endpoints[0]

        if count == 0:
            ep = Endpoint()
            try:
                ep.url = Url.objects.filter(url=url).first()
            except ObjectDoesNotExist:
                ep.url = ""
            ep.port = port
            ep.protocol = protocol
            ep.ip_version = ip_version
            ep.is_dead = False
            ep.discovered_on = datetime.now(pytz.utc)
            ep.save()

            return ep

    @staticmethod
    # while being extermely slow, it sort of works... It's better than waiting for the whole list to download.
    # jet only feature: http://jet.readthedocs.io/en/latest/autocomplete.html
    def autocomplete_search_fields():
        return 'url__url',

    class Meta:
        verbose_name = _('endpoint')
        verbose_name_plural = _('endpoint')


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
        max_length=10,
        help_text="Whether to see this as a http or https proxy",
        default='https'
    )

    address = models.CharField(
        max_length=255,
        help_text="An internet address, including the http/https scheme. Works only on IP. Username / pass can be"
                  "added in the address. For example: https://username:password@192.168.1.1:1337/"
    )

    currently_used_in_tls_qualys_scan = models.BooleanField(
        default=False,
        help_text="Set's the proxy as in use, so that another scanner knows that this proxy is being used at this "
                  "moment. After a scan is completed, the flag has to be disabled. This of course goes wrong with "
                  "crashes. So once in a while, if things fail or whatever, this might have to be resetted."
    )

    is_dead = models.BooleanField(
        default=False,
        help_text="Use the 'declare dead' button to autofill the date. "
                  "If the port is closed, or the endpoint is otherwise"
                  "not reachable over the specified protocol, then mark"
                  "it as dead. A scanner for this port/protocol can also"
                  "declare it dead. This port is closed on this protocol."
                  ""
    )

    manually_disabled = models.BooleanField(
        default=False,
        help_text="Proxy will not be used if manually disabled."
    )

    is_dead_since = models.DateTimeField(
        blank=True,
        null=True
    )

    is_dead_reason = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    check_result = models.CharField(
        max_length=60,
        help_text="The result of the latest 'check proxy' call.",
        default='Unchecked.'
    )

    check_result_date = models.DateTimeField(
        blank=True,
        null=True
    )

    last_claim_at = models.DateTimeField(
        blank=True,
        null=True
    )

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
                  "number makes it easy not to use this proxy anymore."
    )

    @staticmethod
    def add_address(address):
        if not ScanProxy.objects.all().filter(address=address).exists():
            proxy = ScanProxy()
            proxy.address = address
            proxy.protocol = 'https'
            proxy.save()

    def __str__(self):
        if self.is_dead:
            return "✝ %s %s" % (self.pk, self.address)
        else:
            return "%s %s" % (self.pk, self.address)


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

    url = models.ForeignKey(
        Url,
        blank=True,
        null=True,
        on_delete=models.CASCADE
    )

    ip = models.CharField(
        max_length=255,
        help_text="IPv4 or IPv6 Address. Addresses have to be normalized to the compressed "
                  "representation: removing as many zeros as possible. For example:  "
                  "IPv6: abcd:0000:0000:00fd becomes abcd::fd, or "
                  "IPv4: 127.000.000.001 = 127.0.0.1")

    rdns_name = models.CharField(
        max_length=255,
        help_text="The reverse name can be a server name, containing a provider or anything else."
                  "It might contain the name of a yet undiscovered url or hint to a service.",
        blank=True
    )

    discovered_on = models.DateTimeField(blank=True, null=True)

    is_unused = models.IntegerField(default=False,
                                    help_text="If the address was used in the past, but not anymore."
                                              "It's possible that the same address is more than once "
                                              "associated with and endpoint over time, as some providers"
                                              "rotate a set of IP addresses.")

    is_unused_since = models.DateTimeField(blank=True, null=True)

    is_unused_reason = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return "%s %s" % (self.ip, self.discovered_on.date())

    class Meta:
        verbose_name = _('urlip')
        verbose_name_plural = _('urlip')


def one_year_in_the_future():
    return datetime.now(pytz.utc) + timedelta(days=365)


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
        blank=True
    )

    comply_or_explain_explanation = models.TextField(
        max_length=2048,
        help_text="Text that helps explain why this result is not counted in the report. For example: "
                  "a broken scanner or another edge-case that is mainly on the side of the scanning party.",
        verbose_name="explanation",
        default="",
        null=True,
        blank=True
    )

    comply_or_explain_explained_by = models.CharField(
        max_length=512,
        help_text="Please also refer to a thread, discussion or another fact that can be verified.",
        verbose_name="explained by",
        default="",
        null=True,
        blank=True
    )

    comply_or_explain_explained_on = models.DateTimeField(
        help_text="From this moment the rating will be muted.",
        verbose_name="explained on",
        null=True,
        blank=True
    )

    comply_or_explain_case_handled_by = models.CharField(
        max_length=512,
        help_text="Who entered the comply-or-explain information, so it's easy to find the right person to talk to in "
                  "case of follow-ups.",
        verbose_name="case handled by",
        default="",
        null=True,
        blank=True
    )

    comply_or_explain_case_additional_notes = models.TextField(
        max_length=9000,
        help_text="Notes about the scenario for follow up. Things such as phone numbers, mail addresses, contact info."
                  "Will not be exported, but are not secret.",
        verbose_name="additional case notes",
        default="",
        null=True,
        blank=True
    )

    class Meta:
        abstract = True


class PlannedScanStatistic(models.Model):
    at_when = models.DateTimeField()
    data = JSONField()


class PlannedScan(models.Model):
    """
    A planned scan is always performed per url, even if the scan itself is about endpoints. The endpoints can be
    retrieved at a later state,
    """
    url = models.ForeignKey(
        Url,
        on_delete=models.CASCADE
    )

    activity = models.CharField(
        max_length=10,
        default="",
        db_index=True,
        help_text="discover, verify or scan"
        # could be an enum, which saves some data
    )

    scanner = models.CharField(
        # perhaps this should be an int and scanners should be a number. This works also though...
        # more data = more better
        max_length=30,  # internet_nl_v2_mail, known_subdomains, http_security_headers, verify_unresolvable
        default="",
        db_index=True,
        help_text="tlsq, dnssec, http_security_headers, plain_http, internet_nl_mail, dnssec, ftp, dns_endpoints"
        # could be an enum, which saves some data
    )

    state = models.CharField(
        max_length=10,
        default="",
        db_index=True,
        help_text="requested, picked_up, finished, error, timeout"
    )

    """
        WHERE
        requested_at_when >= '%(when)s'
    """
    requested_at_when = models.DateTimeField(
        db_index=False
    )

    last_state_change_at = models.DateTimeField(
        null=True,
    )

    finished_at_when = models.DateTimeField(
        null=True,
        help_text="when finished, timeout, error"
    )

    # add joined index over scanner, activity, state, so queries are faster:
    # see: https://docs.djangoproject.com/en/3.0/ref/models/options/#indexes
    class Meta:
        indexes = [
            models.Index(fields=['scanner', 'activity', 'state'])
        ]


class PlannedScanError(models.Model):
    # since many plannedscans will run just fine, don't add this information to that model.

    planned_scan = models.ForeignKey(
        PlannedScan,
        on_delete=models.CASCADE
    )

    debug_information = models.CharField(
        max_length=512
    )


# https://docs.djangoproject.com/en/dev/topics/db/models/#id6
class GenericScanMixin(ExplainMixin, LatestScanMixin):
    """
    This is a fact, a point in time.
    """
    type = models.CharField(
        max_length=60,
        db_index=True,
        help_text="The type of scan that was performed. Instead of having different tables for each"
                  "scan, this label separates the scans.")
    rating = models.CharField(
        max_length=128,
        default=0,
        help_text="Preferably an integer, 'True' or 'False'. Keep ratings over time consistent."
    )
    explanation = models.CharField(
        max_length=255,
        default=0,
        help_text="Short explanation from the scanner on how the rating came to be."
    )
    evidence = models.TextField(
        max_length=9001,
        default=0,
        help_text="Content that might help understanding the result.",
        blank=True,
    )
    last_scan_moment = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="This gets updated when all the other fields stay the same. If one changes, a"
                  "new scan will be saved, obsoleting the older ones."
    )
    rating_determined_on = models.DateTimeField(
        help_text="This is when the current rating was first discovered. It may be obsoleted by"
                  "another rating or explanation (which might have the same rating). This date "
                  "cannot change once it's set."
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
        ordering = ['-rating_determined_on', ]


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
        return "%s: %s %s on %s" % (self.rating_determined_on.date(), self.type, self.rating, self.endpoint)


class UrlGenericScan(GenericScanMixin):
    """
    Only changes are saved as a scan.
    """
    url = models.ForeignKey(
        Url,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    def __str__(self):
        return "%s: %s %s on %s" % (self.rating_determined_on.date(), self.type, self.rating, self.url)


class EndpointGenericScanScratchpad(models.Model):
    """
    A debugging channel for generic scans.
    You can easily truncate this log after 30 days.
    """
    type = models.CharField(
        max_length=60,
        db_index=True,
        help_text="The type of scan that was performed. Instead of having different tables for each"
                  "scan, this label separates the scans.")
    domain = models.CharField(
        max_length=255,
        help_text="Deprecated. Used when there is no known Endpoint.",
        blank=True,
        null=True
    )
    at_when = models.DateTimeField(
        auto_now_add=True
    )
    data = models.TextField(
        help_text="Whatever data to dump for debugging purposes."
    )


class Screenshot(models.Model):
    endpoint = models.ForeignKey(
        Endpoint, null=True, blank=True, on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    image = models.ImageField(upload_to="screenshots/", height_field="height_pixels", width_field="width_pixels",
                              default=None, null=True)
    width_pixels = models.IntegerField(default=0)
    height_pixels = models.IntegerField(default=0)
    created_on = models.DateTimeField(auto_now_add=True, db_index=True)


class InternetNLV2Scan(models.Model):
    """

    Version 2 of the Internet.nl API is implemented here.

    """
    type = models.CharField(
        max_length=30,
        help_text="mail, mail_dashboard or web",
        blank=True,
        null=True
    )

    scan_id = models.CharField(
        max_length=32,
        help_text="The scan ID that is used to request status and report information.",
        blank=True,
        null=True
    )

    # registered, scanning, finished
    state = models.CharField(
        max_length=200,
        help_text="where the scan is: registered, scanning, creating_report, finished, failed",
        blank=True,
        null=True
    )

    state_message = models.CharField(
        max_length=200,
        help_text="Information about the status, for example error information.",
        blank=True,
        null=True
    )

    last_state_check = models.DateTimeField(
        blank=True,
        null=True
    )

    last_state_change = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When this state changed the last time, so no in-between updates about the state."
    )

    # metadata returned from the scan, contains info about the api version, tracking info, scan type etc.
    metadata = JSONField(
        default=None,
        blank=True,
        null=True
    )

    # this allows filtering during the creation of a scan.
    # todo: what if a url is deleted, this relation should also be deleted, is that happening?
    subject_urls = models.ManyToManyField(
        Url
    )

    # for error recovery and debugging reasons, store the entire result (which can be pretty huge).
    retrieved_scan_report = JSONField(
        default=None,
        blank=True,
        null=True
    )

    def __str__(self):
        return "%s: %s %s" % (self.pk, self.scan_id, self.state)


class InternetNLV2StateLog(models.Model):
    scan = models.ForeignKey(
        InternetNLV2Scan,
        on_delete=models.CASCADE,
    )

    state = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="The state that was registered at a certain moment in time."
    )

    state_message = models.CharField(
        max_length=200,
        help_text="Information about the status, for example error information.",
        blank=True,
        null=True
    )

    last_state_check = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Last time this state was written to this field, which can happen regularly."
    )

    at_when = models.DateTimeField(
        blank=True,
        null=True
    )

    def __str__(self):
        return "%s.%s: %s" % (self.scan.pk, self.pk, self.state)


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

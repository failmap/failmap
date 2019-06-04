# coding=UTF-8
from datetime import datetime, timedelta

import pytz
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.translation import gettext_lazy as _

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

    Explains are available for all scans: GenericUrlScan, GenericEndpointScan, TlsScan, TlsQualysscan, this means
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
                  "a broken scanner or another edge-case that is mainly on the side of the scanning party. Having "
                  "requested the supplier for a fix, or promising a fix should be stored as a promise, not as an "
                  "explanation.",
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


class TlsQualysScan(ExplainMixin, LatestScanMixin):
    """
    Model for scanner tls qualys
    """
    endpoint = models.ForeignKey(Endpoint, on_delete=models.CASCADE)

    # result from the API
    qualys_rating = models.CharField(max_length=3, default=0)  # 0, F, D, C, B, A-, A, A+
    qualys_rating_no_trust = models.CharField(max_length=3, default=0)
    qualys_message = models.CharField(max_length=255, help_text="Whatever Qualys said "
                                                                "about the endpoint",
                                      blank=True,
                                      null=True)

    # scan management
    # Deprecated: pending = models.BooleanField(default=0)  # scan in progress
    # Deprecated: pending_since = models.DateTimeField(null=True, blank=True)

    # This is the last completed scan, we scan often, but the rating doesn't change that much
    # This is just so we can manage when to scan next and to say when we've last checked.
    scan_date = models.DateField(auto_now_add=True)  # completed scan
    scan_time = models.TimeField(auto_now_add=True)  # For database indexes
    last_scan_moment = models.DateTimeField(auto_now_add=True, db_index=True)  # For database indexes

    # This is when the rating was determined. Ratings don't change that much.
    rating_determined_on = models.DateTimeField()

    class Meta:
        managed = True
        db_table = 'scanner_tls_qualys'
        ordering = ['-rating_determined_on', ]

    @property
    def type(self):
        return "tls_qualys"

    def __str__(self):
        return "%s - %s" % (self.scan_date, self.qualys_rating)


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
    width_pixels = models.IntegerField(default=0)
    height_pixels = models.IntegerField(default=0)
    created_on = models.DateTimeField(auto_now_add=True, db_index=True)


class InternetNLScan(models.Model):

    type = models.CharField(
        max_length=30,
        help_text="mail, mail_dashboard or web",
        blank=True,
        null=True
    )

    success = models.BooleanField(
        default=False,
        help_text="If the scan finished successfully."
    )

    started = models.BooleanField(
        default=False,
        help_text="If the scan is started, normally this is a YES."
    )

    """
    during deploy this somehow converts to a datetime(6) NULL... which causes a syntax error.
    this error did not pop up during development, tests or migration during tests. Weird.
    it also doesn't deviate much from the other column specifications with a datetimefield... so wtf.
    DATETIME(6) is the fractional seconds precision. So that is something real and supported. What is the
    syntax error then?
    o your MySQL server version for the right syntax to use near '(6) NULL, `finished` bool NOT NULL, `finished_on`
    datetime(6) NULL, `url` varcha' at line 1"). Is "started_on" or started a reserved word?
    only type is a reserved word. But type is not in the first version of this query.
    https://dev.mysql.com/doc/refman/5.5/en/keywords.html
    can i see the whole query?

    failmap sqlmigrate scanners 0051_internetnlscan

    This is the whole query:
    BEGIN;
    --
    -- Create model InternetNLScan
    --
    CREATE TABLE `scanners_internetnlscan`
    (
        `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
        `success` bool NOT NULL,
        `started` bool NOT NULL,
        `started_on` datetime(6) NULL,
        `finished` bool NOT NULL,
        `finished_on` datetime(6) NULL, `url` varchar(500) NULL,
        `message` varchar(500) NULL
    );
    COMMIT;

    It crashes on the (6) NULL at `started_on`. So what's up?
    This? https://django-mysql.readthedocs.io/en/latest/management_commands/fix_datetime_columns.html
    Server version: 5.5.62-0+deb8u1 (Debian)
    That version doesn't support datetime(6) yet...?
    i guess they dropped 5.5 support in this version of django?

    Python version: 3.6.6
    Django version: 2.1.3
    Failmap version: 1.1+b9ef27fe

    https://dev.mysql.com/doc/refman/5.6/en/fractional-seconds.html
    MySQL 5.6.4 and up expands fractional seconds support for TIME, DATETIME, and TIMESTAMP values, with up to
    microseconds (6 digits) precision:

    With MySQL 5.5, Django uses datetime for DateTimeField, from 5.6 onwards it uses datetime(6) with microseconds.
    super_stitch@faalserver:~# mysql --version
    mysql  Ver 14.14 Distrib 5.5.62, for debian-linux-gnu (x86_64) using readline 6.3

    So this seems to be a bug. I guess we have to upgrade to 5.6?
    I think the django script sees Distrib 5.5.62 which contains "5.6" :) Which would mean we didn't create datetime
    since july this year or the bug was freshly introduced.

    So the issue is probably somewhere in Django.
    The mysql with microseconds came out 5 years ago. And there is no similar issue yet. So now what...

    5.5 support seems to be dropped from django. Rightly so.
    https://code.djangoproject.com/ticket/28552

    And there you also see the microsecond_precision flag dropped.
    'The end of upstream support for MySQL 5.5 is December 2018. Therefore, Django 2.1 (released a couple months
    earlier in August 2018) may set MySQL 5.6 as the minimum version that it supports.'

    Which is also in the release notes: https://docs.djangoproject.com/en/2.1/releases/2.1/
    So we where lucky to be able to run this version at all. So we can stay on an old django version to support legacy
    sql. Which means no support etc. Or move to 1.11 LTS, but that means also a lot of changes and stagnation in
    adoption of new features. I guess we're updating the database then. And if that's a lot of work, set django fixed
    to 2.0
    """
    started_on = models.DateTimeField(
        blank=True,
        null=True
    )

    finished = models.BooleanField(
        default=False,
        help_text="If the scan is complete."
    )

    finished_on = models.DateTimeField(
        blank=True,
        null=True
    )

    status_url = models.TextField(
        max_length=500,
        help_text="The url where the status of the batch scan can be retrieved.",
        blank=True,
        null=True
    )

    message = models.TextField(
        max_length=500,
        help_text="The complete answer retrieved from the server.",
        blank=True,
        null=True
    )

    friendly_message = models.CharField(
        max_length=255,
        help_text="The message from the complete answer. Gives insight into progress of the scan.",
        blank=True,
        null=True
    )


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

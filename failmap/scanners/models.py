# coding=UTF-8
from datetime import datetime

import pytz
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.translation import gettext_lazy as _

from failmap.organizations.models import Url


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


class TlsQualysScan(models.Model):
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

    def __str__(self):
        return "%s - %s" % (self.scan_date, self.qualys_rating)


class TlsScan(models.Model):
    """
    Model for our own TLS scans
    """
    endpoint = models.ForeignKey(Endpoint, on_delete=models.CASCADE)

    # result from the API
    rating = models.CharField(
        max_length=3,
        default="",
        help_text="F, D, C, B, A-, A, A+, T")
    rating_no_trust = models.CharField(
        max_length=3,
        default="",
        help_text="rating when trust issues are ignored"
    )
    explanation = models.CharField(
        max_length=255,
        default=0,
        help_text="Short explanation from the scanner on how the rating came to be."
    )
    evidence = models.TextField(
        max_length=9001,
        default=0,
        help_text="Content that might help understanding the result."
    )

    scan_date = models.DateField(auto_now_add=True)  # completed scan
    scan_time = models.TimeField(auto_now_add=True)  # For database indexes
    last_scan_moment = models.DateTimeField(auto_now_add=True, db_index=True)  # For database indexes

    # This is when the rating was determined. Ratings don't change that much.
    rating_determined_on = models.DateTimeField()

    def __str__(self):
        return "%s - %s" % (self.scan_date, self.rating)

    class Meta:
        verbose_name = _('tlsscan')
        verbose_name_plural = _('tlsscan')


# https://docs.djangoproject.com/en/dev/topics/db/models/#id6
class GenericScanMixin(models.Model):
    """
    This is a fact, a point in time.
    """
    type = models.CharField(
        max_length=60,
        db_index=True,
        help_text="The type of scan that was performed. Instead of having different tables for each"
                  "scan, this label separates the scans.")
    rating = models.CharField(
        max_length=10,
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
        help_text="Content that might help understanding the result."
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
    domain = models.CharField(
        max_length=255,
        help_text="Deprecated. Text value representing the url scanned.",
        null=True,
        blank=True,
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
    when = models.DateTimeField(
        auto_now_add=True
    )
    data = models.TextField(
        help_text="Whatever data to dump for debugging purposes."
    )


class Screenshot(models.Model):
    endpoint = models.ForeignKey(
        Endpoint, null=True, blank=True, on_delete=models.CASCADE)
    domain = models.CharField(max_length=255, help_text="Deprecated. Used when there is no known URL.",
                              blank=True, null=True)
    filename = models.CharField(max_length=255)
    width_pixels = models.IntegerField(default=0)
    height_pixels = models.IntegerField(default=0)
    created_on = models.DateTimeField(auto_now_add=True, db_index=True)


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
    when = models.DateTimeField(auto_now_add=True)
    data = models.TextField()

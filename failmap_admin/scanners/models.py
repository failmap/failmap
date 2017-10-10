# coding=UTF-8
from django.db import models

from failmap_admin.organizations.models import Url


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
    # There was duplication between URL.URL and endpoint.domain. This resulted on both
    # places the same data was stored (increase in database size). Additionally there was no
    # django way to travel between endpoints and urls, which made it impossible to main
    # database independence. Which would then result in the solution being harder to maintain.
    # Therefore we've dropped the domain field and added a foreign key to URL.
    # todo-cancelled: drop domain at the next possible option.
    # We want, for some reason, to also save scans that don't have a URL.
    domain = models.CharField(max_length=255, help_text="This is a legacy field, "
                                                        "used by the scanner. Will be obsoleted "
                                                        "after the incorrectly migrated domains"
                                                        "have been fixed manually in production"
                                                        "and the scanner is ready.")
    url = models.ForeignKey(
        Url, null=True, blank=True)

    # server information
    server_name = models.CharField(max_length=255,
                                   help_text="rdns, gift from the scan, deprecated",
                                   blank=True)  # a gift from the scan
    ip = models.CharField(
        max_length=255,
        help_text="IPv4 or IPv6 Address. Addresses have to be normalized to the compressed "
                  "representation: removing as many zeros as possible. For example:  "
                  "IPv6: abcd:0000:0000:00fd becomes abcd::fd, or "
                  "IPv4: 127.000.000.001 = 127.0.0.1")
    port = models.IntegerField(default=443,
                               help_text="Ports range from 1 to 65535.")  # 1 to 65535
    protocol = models.CharField(
        max_length=20,
        help_text="Mostly application layer protocols, such as HTTP, FTP,"
                  "SSH and so on. For more, read here: "
                  "https://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol")

    discovered_on = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    # Till when the endpoint existed and why it was deleted (or didn't exist at all).
    is_dead = models.IntegerField(default=False,
                                  help_text="If the port is closed, or the endpoint is otherwise"
                                            "not reachable over the specified protocol, then mark"
                                            "it as dead. A scanner for this port/protocol can also"
                                            "declare it dead. This port is closed on this protocol."
                                            "")
    is_dead_since = models.DateTimeField(blank=True, null=True)
    is_dead_reason = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        if self.is_dead:
            return "✝ %s = %s | %s/%s" % (self.domain,  self.ip, self.protocol, self.port)
        else:
            return "%s = %s | %s/%s" % (self.domain, self.ip, self.protocol, self.port)

    def uri_url(self):
        return "%s://%s:%s" % (self.protocol, self.url.url, self.port)

    def uri_ip(self):
        return "%s://%s:%s" % (self.protocol, self.ip, self.port)

    # when testing for ipv4 or ipv6, an endpoint is mutually exclusive.
    def is_ipv4(self):
        return ":" not in self.ip

    def is_ipv6(self):
        return ":" in self.ip


class TlsQualysScan(models.Model):
    """
    Model for scanner tls qualys
    """
    endpoint = models.ForeignKey(Endpoint)

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
    scan_moment = models.DateTimeField(auto_now_add=True, db_index=True)  # For database indexes

    # This is when the rating was determined. Ratings don't change that much.
    rating_determined_on = models.DateTimeField()

    class Meta:
        managed = True
        db_table = 'scanner_tls_qualys'

    def __str__(self):
        return "%s - %s" % (self.scan_date, self.qualys_rating)


class EndpointGenericScan(models.Model):
    """
    This is a fact, a point in time.
    """
    type = models.CharField(
        max_length=60,
        db_index=True,
        help_text="The type of scan that was performed. Instead of having different tables for each"
                  "scan, this label separates the scans.")
    endpoint = models.ForeignKey(
        Endpoint,
        on_delete=models.PROTECT,
        null=True,
        blank=True)
    domain = models.CharField(
        max_length=255,
        help_text="Used when there is no known endpoint.")
    rating = models.CharField(
        max_length=3,
        default=0,
        help_text="Preferably an integer. Keep ratings over time consistent."
    )
    explanation = models.CharField(
        max_length=255,
        default=0,
        help_text="Short explanation from the scanner on how the rating came to be."
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

    def __str__(self):
        return "%s: %s rated %s on %s" % (self.rating_determined_on, self.type, self.rating, self.endpoint)


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
        help_text="Used when there is no known Endpoint."
    )
    when = models.DateTimeField(
        auto_now_add=True
    )
    data = models.TextField(
        help_text="Whatever data to dump for debugging purposes."
    )


class Screenshot(models.Model):
    endpoint = models.ForeignKey(
        Endpoint, null=True, blank=True)
    domain = models.CharField(max_length=255, help_text="Used when there is no known URL.")
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


class State(models.Model):
    """
    A key value system (registry) to help with resuming scanners.
    """
    scanner = models.CharField(max_length=255, unique=True)
    value = models.CharField(max_length=255)
    since = models.DateTimeField(auto_now_add=True)

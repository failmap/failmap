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
    # todo: drop domain at the next possible option.
    domain = models.CharField(max_length=255, help_text="This is a legacy field, "
                                                        "used by the scanner. Will be obsoleted "
                                                        "after the incorrectly migrated domains"
                                                        "have been fixed manually in production"
                                                        "and the scanner is ready.")
    url = models.ForeignKey(
        Url,
        on_delete=models.PROTECT, null=True, blank=True)

    # server information
    server_name = models.CharField(max_length=255, help_text="rdns")  # a gift from the scan
    ip = models.CharField(max_length=255)  # can be either IPv4, IPv6, maybe even a domain...
    port = models.IntegerField(default=443)  # 1 to 65535
    protocol = models.CharField(max_length=20)  # https://en.wikipedia.org/wiki/Transport_layer

    # Till when the endpoint existed and why it was deleted.
    is_dead = models.IntegerField(default=False)  # domain may be dead
    is_dead_since = models.DateTimeField(blank=True, null=True)
    is_dead_reason = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        if self.is_dead:
            return "✝ %s = %s | %s/%s" % (self.domain,  self.ip, self.protocol, self.port)
        else:
            return "%s = %s | %s/%s" % (self.domain, self.ip, self.protocol, self.port)


# todo: to save data, you can also only save the changes in the scan over time.
# and dump the rest / intermediates elsewhere.
class TlsQualysScan(models.Model):
    """
    Model for scanner tls qualys
    """
    endpoint = models.ForeignKey(Endpoint)

    # result from the API
    qualys_rating = models.CharField(max_length=3, default=0)  # 0, F, D, C, B, A-, A, A+
    qualys_rating_no_trust = models.CharField(max_length=3, default=0)

    # scan management
    pending = models.BooleanField(default=0)  # scan in progress
    pending_since = models.DateTimeField(null=True)

    # This is the last completed scan, we scan often, but the rating doesn't change that much
    # This is just so we can manage when to scan next and to say when we've last checked.
    scan_date = models.DateField(auto_now_add=True)  # completed scan
    scan_time = models.TimeField(auto_now_add=True)  # For database indexes
    scan_moment = models.DateTimeField(auto_now_add=True)  # For database indexes

    # This is when the rating was determined. Ratings don't change that much.
    rating_determined_on = models.DateTimeField()

    class Meta:
        managed = True
        db_table = 'scanner_tls_qualys'

    def __str__(self):
        return "%s - %s" % (self.scan_date, self.qualys_rating)


# A debugging table to help with API interactions.
# This can be auto truncated after a few days.
class TlsQualysScratchpad(models.Model):
    """
    A debugging channel for all communications with Qualys.
    You can easily truncate this log after 30 days.
    """
    domain = models.CharField(max_length=255)
    when = models.DateTimeField(auto_now_add=True)
    data = models.TextField()

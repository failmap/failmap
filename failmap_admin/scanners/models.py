from django.db import models


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
    """
    # this is no foreign key, as history is desired. We want to see our impact.
    domain = models.CharField(max_length=255)

    # server information
    server_name = models.CharField(max_length=255)  # a gift from the scan
    ip = models.CharField(max_length=255)  # can be either IPv4, IPv6, maybe even a domain...
    port = models.IntegerField(default=443)  # 1 to 65535
    protocol = models.CharField(max_length=20)  # https://en.wikipedia.org/wiki/Transport_layer

    # Till when the endpoint existed and why it was deleted.
    is_dead = models.IntegerField(default=False)  # domain may be dead
    is_dead_since = models.DateTimeField(blank=True, null=True)
    is_dead_reason = models.CharField(max_length=255, blank=True, null=True)


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

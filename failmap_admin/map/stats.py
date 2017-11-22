import datetime
import logging

import pytz
import tldextract

from failmap_admin.map.determineratings import (relevant_endpoints_at_timepoint,
                                                relevant_urls_at_timepoint)
from failmap_admin.map.models import UrlRating
from failmap_admin.organizations.models import Organization, Url
from influxdb import InfluxDBClient

# https://docs.influxdata.com/influxdb/v1.3/tools/shell/#influx-arguments
# https://docs.influxdata.com/influxdb/v1.3/tools/api/#write
# http://influxdb-python.readthedocs.io/en/latest/examples.html

# brew install influxdb
# brew install grafana
# brew services start influxdb  # (http://localhost:8086/)
# brew services start grafana  # http://localhost:3000/login, use admin/admin to log in
# # add datasource:
# influx -precision rfc3339
# CREATE DATABASE elger_test
# exit
# in grafana, make a new dashboard. and then build your queries :)
# influxdb to 127.0.0.1 in /etc/hosts
# todo: environment variables.

# clean the test db:
# influx
# drop database elger_test
# create database elger_test

logger = logging.getLogger(__package__)


# create the smallest, most complete and lowest possible granulation for the data.
# not only post the changes, post all data that stays the same too, every day: only that way you can
# see the impact of changes
def update_stats():
    client = InfluxDBClient("influxdb", 8086, "", "", "elger_test", retries=50, timeout=10, verify_ssl=False)

    first_rating = UrlRating.objects.earliest("when")
    first_day = first_rating.when
    is_today = False
    processed_day = first_day - datetime.timedelta(days=1)
    today = datetime.datetime.now(pytz.utc)
    metrics = {}

    logger.info("Creating stats, this can take a while. Get a cup of tea and say hi to the cat.")
    logger.info("Creating %s days of metrics, starting on %s." % ((today - first_day).days, first_day.date()))

    while not is_today:
        processed_day += datetime.timedelta(days=1)
        logger.info("%s days to go, currently on %s" % ((today - processed_day).days, processed_day.date()))

        # do add thigns for today, but not tomorrow.
        if processed_day.date() == today.date():
            is_today = True

        metrics = metrics_per_day(processed_day.date(), metrics)
        logger.info("This days total metrics: %s" % len(metrics.values()))
        if not client.write_points(metrics.values()):
            raise SyntaxError("Something went wrong inserting points. Points: %s" % metrics.values())

    logger.info("Done creating stats.")
    return


# warning: server needs mysql_tzinfo_to_sql for date filtering to work
# https://github.com/django/django/commit/62f282a265ae7f8d051f7ce79788cfc1a84d1a24
# https://dev.mysql.com/doc/refman/5.5/en/mysql-tzinfo-to-sql.html
def metrics_per_day(date, metrics):
    """

    :param date: a date to get changes.
    :param metrics: dictionary with previous metrics, to re-post metrics for other days if they don't change. Only the
    metrics that change on supplied date are overwritten.
    :return: metrics
    """

    # storing is_dead is not possible, as those urls will have no url ratings anymore (as we only ...)
    metrics = remove_irrelevant_urls(date, metrics)
    metrics = remove_irrelevant_endpoints(date, metrics)

    # mysql returns an empty queryset, while sqlite does the job well. why?
    for url_rating in UrlRating.objects.all().filter(when__date=date):

        if 'endpoints' not in url_rating.calculation.keys():
            logger.info("No endpoints in this calculation. Url died? Rating id: %s " % url_rating.id)
            continue

        for endpoint in url_rating.calculation['endpoints']:
            for rating in endpoint['ratings']:
                for organization in url_rating.url.organization.all():

                    if 'low' not in rating.keys():
                        # logger.info("No (low) rating in this endpoint. Is it a repeated finding? Those should "
                        #             "have been all gone by now. What went wrong? %s" % endpoint)
                        continue

                    hsah = "%s%s%s%s%s%s%s%s" % (endpoint['ip'], endpoint['port'], endpoint['protocol'],
                                                 rating['type'], url_rating.url.url, organization.name,
                                                 organization.type.name, organization.country.name)

                    metrics[hsah] = {
                        "measurement": "url_rating",
                        "tags": {
                            "ip_version": endpoint['ip'],
                            "port": endpoint['port'],
                            "protocol": endpoint['protocol'],
                            "scan_type": rating['type'],
                            "url": url_rating.url.url,
                            "subdomain": tldextract.extract(url_rating.url.url).subdomain,
                            "suffix": tldextract.extract(url_rating.url.url).suffix,
                            "organization": organization.name,
                            "organization_type": organization.type.name,
                            "country": organization.country.name,

                            # Given only relevant urls have an urlrating, these values will true.
                            # Its possible to filter this better, comparing it to time. That should be done in
                            # a separate loop. Doing that might remove the need to remove irrelevant endpoints/urls
                            # as they can be filtered in grafana queries.

                            #
                            # "url_is_dead": url_rating.url.is_dead_since.date() >= date,
                            # "url_not_resolvable": url_rating.url.not_resolvable_since.date() >= date,
                            # "endpoint_is_dead": endpoint.is_dead_since.date() >= date,
                            # "any_is_dead": any([url_rating.url.is_dead_since.date() >= date,
                            #                     url_rating.url.not_resolvable_since.date() >= date,
                            #                     endpoint.is_dead_since.date() >= date]),

                            # if filtering out dead endpoints and urls:
                            # you need this, since multiple organizations can have the same names, country and type
                            # but technically they are different and can contain different urls.
                            "organization_pk": organization.id,
                            "url_pk": url_rating.url.id
                        },
                        "time": rating['last_scan'],
                        "fields": {
                            "low": rating['low'],
                            "medium": rating['medium'],
                            "high": rating['high'],
                            "points": rating['points']
                        }
                    }

                    # logger.debug(hsah) and logger.debug(metrics[hsah])

        # [logger.debug("%s, %s" % (metric, metrics[metric]['fields'])) for metric in metrics]

    # all metrics that where measured yesterday, update them for today, as a "fill" method.
    # (the only thing special about this fill method is that only the relevant urls/endpoints get added to metrics)
    # but we might / should just filter that in queries and add everything.
    # maybe a "fill" will work if we can filter on the fill.
    metrics = update_old_metrics_to_today(date, metrics)

    return metrics


# all metrics that don't have a value today where not given a new value. So update these older metrics to today.
# this has purposefully not made to do: day +1 day, as that might be non deterministic
# should use dateutil?
def update_old_metrics_to_today(date, metrics):
    for metric in metrics:
        metric_date = datetime.datetime.strptime(metrics[metric]["time"], "%Y-%m-%dT%H:%M:%S+00:00")
        metric_date = pytz.utc.localize(metric_date)
        if metric_date.date() != date:
            metrics[metric]["time"] = str(metric_date.replace(
                year=date.year, month=date.month, day=date.day).isoformat())

    return metrics


# not used, as the is_dead and such can be determined in grafana / query.
def remove_irrelevant_urls(date, metrics):

    if not metrics:
        return {}

    # extract organizations using name, type.
    organization_ids = [x["tags"]["organization_pk"] for x in metrics.values()]
    organizations = Organization.objects.all().filter(pk__in=organization_ids)  # slow query, unfortunately.

    # and also remove any url that has died or whatever:
    relevant_urls = relevant_urls_at_timepoint(organizations=organizations, when=date)

    # now remove all the non-relevant urls from the metrics
    relevant_url_ids = [x.pk for x in relevant_urls]

    relevant_metrics = {}
    for metric in metrics:
        if metrics[metric]["tags"]["url_pk"] in relevant_url_ids:
            relevant_metrics[metric] = metrics[metric]

    return relevant_metrics


# there might be measurements even after the url is not relevant.
def remove_irrelevant_endpoints(date, metrics):

    if not metrics:
        return {}

    # logger.debug(metrics)

    url_ids = [x["tags"]["url_pk"] for x in metrics.values()]
    urls = Url.objects.all().filter(pk__in=url_ids)

    relevant_endpoints = relevant_endpoints_at_timepoint(urls=urls, when=date)

    relevant_metrics = {}
    for relevant_endpoint in relevant_endpoints:
        for metric in metrics:
            if all([metrics[metric]["tags"]["ip_version"] == relevant_endpoint.ip_version,
                    metrics[metric]["tags"]["port"] == relevant_endpoint.port,
                    metrics[metric]["tags"]["protocol"] == relevant_endpoint.protocol,
                    metrics[metric]["tags"]["url"] == relevant_endpoint.url.url]):
                relevant_metrics[metric] = metrics[metric]

    return relevant_metrics


def poorly_escape(value: str):
    """
    If a tag key, tag value, or field key contains a space , comma ,, or an equals sign = it must be escaped using the
    backslash character \. Backslash characters do not need to be escaped. Commas , and spaces will also need to be
    escaped for measurements, though equals signs = do not.
    """
    return value.replace(" ", "\ ").replace(",", "\,").replace("=", "\=")

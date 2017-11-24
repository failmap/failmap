import datetime
import logging

import pytz
import tldextract
from dateutil import rrule
from influxdb import InfluxDBClient

from failmap_admin.map.models import UrlRating
from failmap_admin.organizations.models import Url

"""

Influxdb Documentation:
https://docs.influxdata.com/influxdb/v1.3/tools/shell/#influx-arguments
https://docs.influxdata.com/influxdb/v1.3/tools/api/#write
http://influxdb-python.readthedocs.io/en/latest/examples.html

Running influx and grafana on your (mac) development machine:

brew install influxdb
brew install grafana
brew services start influxdb
brew services start grafana

Influxdb runs on port 8086: http://localhost:8086/
Grafana runs on port 3000: http://localhost:3000/login
Grafana login: admin/admin

Install the grafana pie chart plugin:
grafana-cli plugins install grafana-piechart-panel
brew service grafana-server restart

Log into grafana via a shell and create a database:
influx
create database elger_test
exit

Add the hostname influxdb to your hosts file:
influxdb 127.0.0.1
Hosts file is usually at /etc/hosts

Then run this script and start building dashboards in grafana.
"""

# todo: environment variables.

logger = logging.getLogger(__package__)

"""
The end goal of these ratings is to visualize changes over time.

"""


def update_stats():
    client = InfluxDBClient("influxdb", 8086, "", "", "elger_test", retries=50, timeout=10, verify_ssl=False)
    logger.info("Creating stats, this can take a while. Get a cup of tea and say hi to the cat.")

    for url in Url.objects.all():
        logger.info("Adding metrics for %s" % url)
        metrics = metrics_per_url(url)
        logger.info("Metrics found: %s" % len(metrics))
        if metrics:
            if not client.write_points(metrics):
                raise SyntaxError("Something went wrong inserting points. DB offline? Wrong syntax?")

    logger.info("Done creating stats.")
    return


# the ordering of url_ratings is really important here.
# we're not using django filter as that adds a database round trip
def todays_relevant_url_rating(dt, url_ratings):

    rev_url_ratings = reversed(url_ratings)
    for url_rating in rev_url_ratings:
        # logger.debug("%s %s", dt, url_rating.when)
        # logger.debug("%s", url_rating.when - dt)
        if url_rating.when <= dt:
            return url_rating


def metrics_per_url(url):
    """
    This fully trusts that an url rating contains all manipulations of the url and all related endpoints.
    So if an endpoint was in a previous rating, but not in this one, the endpoint died (or there where no relevant
    metrics for it to store it in the url rating).

    The best choice is to have the smallest granularity for ratings: these are ratings on an endpoint per day.

    Url ratings are stored using deduplication. This saves several gigabytes of data.
    Url ratings on the test dataset = 22013 items. The average url rating is about 3 kilobyte. = 64 megabyte.
    Without deduplication it would be urls * days * 3kb. = 7000 * 400 * 3kb = 8 gigabyte.

    Thus this function applies duplication to "fill" periods between different urlratings. That is the way grafana
    want's to see the data. You can't do a fill in influx, as it doesn't know when a url/endpoint stops existing etc.
    """

    url_ratings = UrlRating.objects.all().filter(url=url).order_by('when')  # earliest first (asc)

    if not url_ratings:
        return []

    # duplicate the url_ratings
    earliest_rating_date = url_ratings[0].when
    now = datetime.datetime.now(pytz.utc)
    metrics = []
    yesterdays_metrics = []
    yesterdays_relevant_rating = None

    for dt in rrule.rrule(rrule.DAILY, dtstart=earliest_rating_date, until=now):
        todays_metrics = []

        # prevent insertion of duplicate points on different times. Also for the metric of today.
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc)

        # get the rating that is earlier than the next rating
        relevant_rating = todays_relevant_url_rating(dt, url_ratings)

        # if the relevant rating today is the same as yesterday, then we can simply copy yesterdays ratings
        # and change the date. That save a few database hits, making it 4x as fast on the test dataset.
        if relevant_rating == yesterdays_relevant_rating:
            # update yesterdays metrics: to todays date.
            for metric in yesterdays_metrics:
                metric_copy = metric.copy()
                metric_copy["time"] = dt
                todays_metrics.append(metric_copy)
        else:
            yesterdays_relevant_rating = relevant_rating

            if 'endpoints' not in relevant_rating.calculation.keys():
                logger.info("No endpoints in this calculation. Url died or became not resolvable. "
                            "No metrics needed anymore :).")
                return []

            for endpoint in relevant_rating.calculation['endpoints']:
                for rating in endpoint['ratings']:
                    for organization in relevant_rating.url.organization.all():

                        if 'low' not in rating.keys():
                            # logger.info("No (low) rating in this endpoint. Is it a repeated finding? Those should "
                            #             "have been all gone by now. What went wrong? %s" % endpoint)
                            continue

                        todays_metrics.append({
                            "measurement": "url_rating",
                            "tags": {
                                "ip_version": endpoint['ip'],
                                "port": endpoint['port'],
                                "protocol": endpoint['protocol'],
                                "scan_type": rating['type'],
                                "url": relevant_rating.url.url,
                                "subdomain": tldextract.extract(relevant_rating.url.url).subdomain,
                                "suffix": tldextract.extract(relevant_rating.url.url).suffix,
                                "organization": organization.name,
                                "organization_type": organization.type.name,
                                "country": organization.country.name,
                                "explanation": rating['explanation'],
                            },
                            "time": dt,
                            "fields": {
                                "low": rating['low'],
                                "medium": rating['medium'],
                                "high": rating['high'],
                                "points": rating['points'],
                                "exists": 1,
                            }
                        })

        metrics += todays_metrics
        yesterdays_metrics = todays_metrics

    return metrics

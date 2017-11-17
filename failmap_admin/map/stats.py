import logging
import time
from calendar import timegm

from influxdb import InfluxDBClient

from .models import UrlRating

# https://docs.influxdata.com/influxdb/v1.3/tools/shell/#influx-arguments
# https://docs.influxdata.com/influxdb/v1.3/tools/api/#write
# http://influxdb-python.readthedocs.io/en/latest/examples.html

logger = logging.getLogger(__package__)


# create the smallest, most complete and lowest possible granulation for the data.
def update_stats():
    client = InfluxDBClient("influxdb", 8086, "admin", "admin", "elger_test")

    url_ratings = UrlRating.objects.all()
    logger.info("Creating stats, this can take a while. Get a cup of tea and say hi to the cat.")
    for url_rating in url_ratings:
        for endpoint in url_rating.calculation['endpoints']:
            for rating in endpoint['ratings']:
                for organization in url_rating.url.organization.all():
                    metrics = [
                        {
                            "measurement": "url_rating",
                            "tags": {
                                "ip_version": endpoint['ip'],
                                "port": endpoint['port'],
                                "protocol": endpoint['protocol'],
                                "scan_type": poorly_escape(rating['type']),
                                "url": poorly_escape(url_rating.url.url),
                                "organization": poorly_escape(organization.name),
                                "organization_type": poorly_escape(organization.type.name),
                                "country": poorly_escape(organization.country.name)
                            },
                            # epoch time, from isotime in UTC
                            "time": timegm(time.strptime(rating['last_scan'], "%Y-%m-%dT%H:%M:%S+00:00")),
                            "fields": {
                                "low": rating['low'],
                                "medium": rating['medium'],
                                "high": rating['high'],
                                "points": rating['points']
                            }
                        }
                    ]
                    client.write_points(metrics)

    logger.info("Done creating stats.")
    return


def poorly_escape(value: str):
    """
    If a tag key, tag value, or field key contains a space , comma ,, or an equals sign = it must be escaped using the
    backslash character \. Backslash characters do not need to be escaped. Commas , and spaces will also need to be
    escaped for measurements, though equals signs = do not.
    """
    return value.replace(" ", "\ ").replace(",", "\,").replace("=", "\=")

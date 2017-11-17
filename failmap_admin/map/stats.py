import logging
import subprocess
import time
from calendar import timegm

from .models import UrlRating

# https://docs.influxdata.com/influxdb/v1.3/tools/shell/#influx-arguments
# https://docs.influxdata.com/influxdb/v0.9/write_protocols/write_syntax/#http


logger = logging.getLogger(__package__)


# create the smallest, most complete and lowest possible granulation for the data.
def update_stats():
    url_ratings = UrlRating.objects.all()

    for url_rating in url_ratings:
        for endpoint in url_rating.calculation['endpoints']:
            for rating in endpoint['ratings']:
                for organization in url_rating.url.organization.all():
                    tags = "url_rating,ip_versie=%s,port=%s,protocol=%s,scan_type=%s,url=%s,organization=%s," \
                           "organization_type=%s,country=%s" % (
                               endpoint['ip'], endpoint['port'], endpoint['protocol'], poorly_escape(rating['type']),
                               poorly_escape(url_rating.url.url),
                               poorly_escape(organization.name),
                               poorly_escape(organization.type.name),
                               poorly_escape(organization.country.name))

                    values = "low=%s,medium=%s,high=%s,points=%s" % (
                        rating['low'], rating['medium'], rating['high'], rating['points'])

                    utc_time = time.strptime(rating['last_scan'], "%Y-%m-%dT%H:%M:%S+00:00")
                    epoch_time = timegm(utc_time)

                    data = "%s %s %s" % (tags, values, epoch_time)
                    logger.debug(data)
                    subprocess.call(
                        ['curl', '-s', '-XPOST', '"influxdb:8086/write?db=elger_test&precision=s"',
                         '--data-binary', data])
    print("Jobs done.")
    return


def poorly_escape(value: str):
    """
    If a tag key, tag value, or field key contains a space , comma ,, or an equals sign = it must be escaped using the
    backslash character \. Backslash characters do not need to be escaped. Commas , and spaces will also need to be
    escaped for measurements, though equals signs = do not.
    """
    return value.replace(" ", "\ ").replace(",", "\,").replace("=", "\=")

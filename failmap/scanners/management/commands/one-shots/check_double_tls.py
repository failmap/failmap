import logging

from django.core.management.base import BaseCommand

log = logging.getLogger(__package__)


class Command(BaseCommand):
    """
    This serves as documentation for a legacy issue. If the issue pops up again, these queries and documentation
    might be able to help solving the problem, though it is doubtful this will pop up ever again.

    We've got a support request that stated scans where not updating. Confirmed that the website showed outdated data.
    Looking at the database on the TLS scans, we found two records on the same endpoint.

    12418 IPv4 https/443 | [13708] langparkeren.amsterdam.nl	A	A	Ready	27 oktober 2017 14:35 22 september 2017
    12417 IPv4 https/443 | [13708] langparkeren.amsterdam.nl	A	A	Ready	5 mei 2018 20:31 22 september 2017

    The second one, with the lower ID has the TLS scan updates. So scans where performed. The one with the higher ID
    is automatically selected in the map and report result set due to efficiency reasons.

    Weird things:
    - Both first ratings have the same creation date.
    - The system was not meant to create multiple the same scans on the same endpoint.

    This seems to be a bug with endpoints created on the same moment. Amsterdam has another endpoint that is not
    updated correctly. avproxy.vga.amsterdam.nl. On ipv4. Shows a scan of week 2017/43. Here we see the same pattern:
    there are two created on the same moment and the TLS scan is saved to the oldest one.

    We can fix this in several ways:
    - in TLS only save it to the one with the highest ID. This seems to be a garbage fix as there should not be dupes
      in the first place.
    - figure out how many there are with the same creation date that point to the same endpoint (and learn from it).
      we're choosing this one.

    The first check is to gain insight into the scope of the problem, and to see if it still occurs.
    It doesn't still occur it seems, as the creation dates are well in the past.

    It seems that this issue comes from removing the IP from the endpoint table. These urls are known for having
    more than one IP (sip, iburgerzaken...) and many of them still have 0 ratings from qualys which we stopped using.

    Issue:
    Sometimes the rating gets appended to the lower ID, sometimes to the higher. That indicates that this part of
    the code is not deterministic. The reason not everyone complained is that the amount of urls of amsterdam is
    much larger and they are much more likely to see if things are off. Thankfully they did and now we can fix it :)

    This issue also happened on endpointgenericscan.

    IPv4 https/443 | [4832] www.amsterdam.nl X-Content-Type-Options	True nosniff 12 november 2017 .	3 oktober 2017 13:49
    IPv4 https/443 | [4832] www.amsterdam.nl X-Content-Type-Options	True nosniff 8 mei 2018 .	    3 oktober 2017 13:49

    Two actions:
    - We should clean the DB, remove the doubles and retain the one with the most recent scan.
    ? We should match with the highest ID when the rating_determined_on are the same (and some integrity bug sneeked in)
    - Should we be weary that rating determined on and endpoint_id cannot be the same? We can make a rule for this
      so we will see exceptions happen.

    """

    help = __doc__

    def handle(self, *args, **options):
        """
        # [X] Verified that these manual querys return the same on MySQL and SQLlite.

        # Remediation strategy:
        # Find all endpoints of a certain double, keep the one with the last scan moment, ditch the others.
        :param args:
        :param options:
        :return:
        """

        # Amsterdam has 82 doubles.
        # There is a total of 483 doubles. With 1469 endpoints. Removing all doubles: 1469 - 483 = 986 removed.
        """
        MYSQL / SQLITE:

        SELECT endpoint_id, url, COUNT(rating_determined_on) FROM scanner_tls_qualys
        INNER JOIN scanners_endpoint ON (endpoint_id = scanners_endpoint.id)
        INNER JOIN url ON (url_id = url.id)
        WHERE url LIKE '%%'
        group by endpoint_id, rating_determined_on
        HAVING COUNT(rating_determined_on) > 1
        ORDER BY scan_date DESC
        """

        # deletes 181 rows...
        # Only saves the newer record.
        # This does not work in one step in MySQL. So we need a temp table:
        """
        SQLITE:

        DELETE FROM scanner_tls_qualys WHERE ID IN (SELECT one.id FROM scanner_tls_qualys AS one
        INNER JOIN scanner_tls_qualys AS two ON (one.endpoint_id = two.endpoint_id)
        WHERE one.rating_determined_on = two.rating_determined_on
        AND one.last_scan_moment < two.last_scan_moment)
        """

        """
        MYSQL:

        CREATE TEMPORARY TABLE IF NOT EXISTS double_tls_different AS (SELECT one.id FROM scanner_tls_qualys AS one
        INNER JOIN scanner_tls_qualys AS two ON (one.endpoint_id = two.endpoint_id)
        WHERE one.rating_determined_on = two.rating_determined_on
        AND one.last_scan_moment < two.last_scan_moment)

        DELETE FROM scanner_tls_qualys WHERE ID IN (SELECT id FROM double_tls_different);
        """

        # now delete the ones with the same scan moment AND same rating detemined on.
        # deletes 805 records. For a total of 986 records removed. Just like predicted.
        """
        SQLITE:
            DELETE FROM scanner_tls_qualys WHERE ID IN (SELECT one.id FROM scanner_tls_qualys AS one
                INNER JOIN scanner_tls_qualys AS two ON (one.endpoint_id = two.endpoint_id)
            WHERE one.rating_determined_on = two.rating_determined_on AND
            one.last_scan_moment = two.last_scan_moment
            AND one.id < two.id)
        """

        """
        MYSQL:
        CREATE TEMPORARY TABLE IF NOT EXISTS double_tls_same AS (SELECT one.id FROM scanner_tls_qualys AS one
                INNER JOIN scanner_tls_qualys AS two ON (one.endpoint_id = two.endpoint_id)
            WHERE one.rating_determined_on = two.rating_determined_on AND
            one.last_scan_moment = two.last_scan_moment
            AND one.id < two.id)

        DELETE FROM scanner_tls_qualys WHERE ID IN (SELECT id FROM double_tls_same);
        """

        #
        # Endpoint genericscans.
        # 500 rows, 1301 endpoints (counted in excel). There will be 1301-500 removed = 801
        """
        SQLITE / MYSQL:

        SELECT COUNT(rating_determined_on) FROM scanners_endpointgenericscan
        INNER JOIN scanners_endpoint ON (endpoint_id = scanners_endpoint.id)
        INNER JOIN url ON (url_id = url.id)
        WHERE url LIKE '%%'
        group by type, endpoint_id, rating_determined_on
        HAVING COUNT(rating_determined_on) > 1
        """

        # deletes 724 rows in endpointgenericscan, only saving the newer ones
        """
        SQLITE:
            DELETE FROM scanners_endpointgenericscan WHERE ID IN (
                SELECT one.id FROM scanners_endpointgenericscan AS one
                INNER JOIN scanners_endpointgenericscan AS two
                ON (one.endpoint_id = two.endpoint_id AND one.type = two.type)
                WHERE one.rating_determined_on = two.rating_determined_on
                AND one.last_scan_moment < two.last_scan_moment)
        """

        """
        MYSQL:
        CREATE TEMPORARY TABLE IF NOT EXISTS double_epg_different AS (
                SELECT one.id FROM scanners_endpointgenericscan AS one
                INNER JOIN scanners_endpointgenericscan AS two
                ON (one.endpoint_id = two.endpoint_id AND one.type = two.type)
                WHERE one.rating_determined_on = two.rating_determined_on
                AND one.last_scan_moment < two.last_scan_moment
        )

        DELETE FROM scanners_endpointgenericscan WHERE ID IN (SELECT id FROM double_epg_different);
        """

        # deletes double records, only saving the one with highest ID.
        # deletes 77 rows. Totalling for 801 double rows.
        """
        SQLITE:
            DELETE FROM scanners_endpointgenericscan WHERE ID IN (
                SELECT one.id FROM scanners_endpointgenericscan AS one
                INNER JOIN scanners_endpointgenericscan AS two
                ON (one.endpoint_id = two.endpoint_id
                    AND one.type = two.type
                    AND one.rating_determined_on = two.rating_determined_on
                    AND one.last_scan_moment = two.last_scan_moment)
                AND one.id < two.id)
        """

        """
        MYSQL
        CREATE TEMPORARY TABLE IF NOT EXISTS double_epg_same AS (
                SELECT one.id FROM scanners_endpointgenericscan AS one
                INNER JOIN scanners_endpointgenericscan AS two
                ON (one.endpoint_id = two.endpoint_id
                    AND one.type = two.type
                    AND one.rating_determined_on = two.rating_determined_on
                    AND one.last_scan_moment = two.last_scan_moment)
                AND one.id < two.id
        )

        DELETE FROM scanners_endpointgenericscan WHERE ID IN (SELECT id FROM double_epg_same);
        """

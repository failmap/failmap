import calendar
import logging
from collections import OrderedDict
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import List, Tuple

import pytz
import simplejson as json
from celery import group
from deepdiff import DeepDiff
from django.db.models import Count

from websecmap.celery import Task, app
from websecmap.map.logic.map import get_map_data, get_reports_by_ids
from websecmap.map.logic.map_health import update_map_health_reports
from websecmap.map.map_configs import filter_map_configs
from websecmap.map.models import HighLevelStatistic, MapDataCache, OrganizationReport, VulnerabilityStatistic
from websecmap.organizations.models import Organization, OrganizationType, Url
from websecmap.reporting.report import (
    START_DATE,
    aggegrate_url_rating_scores,
    get_allowed_to_report,
    get_latest_urlratings_fast,
    recreate_url_reports,
    relevant_urls_at_timepoint,
    significant_moments,
)
from websecmap.scanners import ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES
from websecmap.scanners.scanner.__init__ import q_configurations_to_report

log = logging.getLogger(__package__)

# websecmap.scanners.ALL_SCAN_TYPES is too much, as some providers give dozens of results.
# What we want to show is a lot less,
# and therefore this is used. The published scan_types are listed at index.html, in javascript.
# This should be made into python and then exported to JS (nearly the same syntax).
# Look at index.html...

PUBLISHED_ENDPOINT_SCAN_TYPES = [
    "ftp",
    "plain_https",
    "http_security_header_strict_transport_security",
    "http_security_header_x_content_type_options",
    "http_security_header_x_frame_options",
    "http_security_header_x_xss_protection",
    "tls_qualys_certificate_trusted",
    "tls_qualys_encryption_quality",
    "internet_nl_mail_starttls_tls_available",
    "internet_nl_mail_auth_spf_exist",
    "internet_nl_mail_auth_dkim_exist",
    "internet_nl_mail_auth_dmarc_exist",
]

PUBLISHED_URL_SCAN_TYPES = ["DNSSEC"]

PUBLISHED_SCAN_TYPES = PUBLISHED_ENDPOINT_SCAN_TYPES + PUBLISHED_URL_SCAN_TYPES


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """
    Compose taskset to rebuild specified organizations/urls.
    """

    if endpoints_filter:
        raise NotImplementedError("This scanner does not work on a endpoint level.")

    log.info("Organization filter: %s" % organizations_filter)
    log.info("Url filter: %s" % urls_filter)

    # Only displayed configurations are reported. Because why have reports on things you don't display?
    # apply filter to organizations (or if no filter, all organizations)
    organizations = Organization.objects.filter(q_configurations_to_report("organization"), **organizations_filter)

    log.debug("Organizations: %s" % len(organizations))

    # Create tasks for rebuilding ratings for selected organizations and urls.
    # Wheneven a url has been (re)rated the organization for that url need to
    # be (re)rated as well to propagate the result of the url rate. Tasks will
    # be created per organization to first rebuild all of this organizations
    # urls (depending on url filters) after which the organization rating will
    # be rebuild.

    tasks = []
    for organization in organizations:
        # todo: organizations that have no endpoints could get a default rating, which is much quicker
        #  than iterating all organizations. But it does not save too much time...
        urls = (
            Url.objects.filter(
                q_configurations_to_report(),
                organization=organization,
                **urls_filter
                # To save time, only acccept urls that have at least one endpoint.
            )
            .annotate(n_endpoints=Count("endpoint"))
            .filter(n_endpoints__gt=0)
        )
        if not urls:
            # can still add an empty organization rating even though there is nothing to show. Will create an
            # empty gray region.
            tasks.append(default_organization_rating.si([organization.pk]))
            continue

        # make sure default organization rating is in place
        tasks.append(recreate_url_reports.si(urls) | create_organization_reports_now.si([organization.pk]))

    if not tasks:
        log.error("Could not rebuild reports, filters resulted in no tasks created.")
        log.debug("Organization filter: %s" % organizations_filter)
        log.debug("Url filter: %s" % urls_filter)
        log.debug("urls to display: %s" % q_configurations_to_report())
        log.debug("organizations to display: %s" % q_configurations_to_report("organization"))
        return group()

    log.debug("Number of tasks: %s" % len(tasks))

    # finally, rebuild the graphs (which can mis-matchi a bit if the last reports aren't in yet. Will have to do for now
    # mainly as we're trying to get away from canvas and it's buggyness.

    if organizations_filter.get("country__in", None):
        tasks.append(calculate_vulnerability_statistics.si(1, organizations_filter["country__in"]))
        tasks.append(calculate_map_data.si(1, organizations_filter["country__in"]))
        tasks.append(calculate_high_level_stats.si(1, organizations_filter["country__in"]))
        tasks.append(update_map_health_reports.si(PUBLISHED_SCAN_TYPES, 1, organizations_filter["country__in"]))
    elif organizations_filter.get("country", None):
        tasks.append(calculate_vulnerability_statistics.si(1, [organizations_filter["country"]]))
        tasks.append(calculate_map_data.si(1, [organizations_filter["country"]]))
        tasks.append(calculate_high_level_stats.si(1, [organizations_filter["country"]]))
        tasks.append(update_map_health_reports.si(PUBLISHED_SCAN_TYPES, 1, [organizations_filter["country"]]))
    else:
        tasks.append(calculate_vulnerability_statistics.si(1))
        tasks.append(calculate_map_data.si(1))
        tasks.append(calculate_high_level_stats.si(1))
        tasks.append(update_map_health_reports.si(PUBLISHED_SCAN_TYPES, 1))

    task = group(tasks)

    return task


@app.task(queue="reporting")
def calculate_vulnerability_statistics(days: int = 366, countries: List = None, organization_types: List = None):
    log.info("Calculation vulnerability graphs")

    map_configurations = filter_map_configs(countries=countries, organization_types=organization_types)

    for map_configuration in map_configurations:
        scan_types = set()  # set instead of list to prevent checking if something is in there already.
        scan_types.add("total")  # the total would be separated per char if directly passed into set()
        organization_type_id = map_configuration["organization_type"]
        country = map_configuration["country"]

        # for the entire year, starting with oldest (in case the other tasks are not ready)
        for days_back in list(reversed(range(0, days))):
            measurement = {
                "total": {
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "ok_urls": 0,
                    "ok_endpoints": 0,
                    "applicable_endpoints": 0,
                    "applicable_urls": 0,
                }
            }
            when = datetime.now(pytz.utc) - timedelta(days=days_back)
            log.info("Days back:%s Date: %s" % (days_back, when))

            # delete this specific moment as it's going to be replaced, so it's not really noticable an update is
            # taking place.
            VulnerabilityStatistic.objects.all().filter(
                at_when=when, country=country, organization_type=OrganizationType(pk=organization_type_id)
            ).delete()

            # about 1 second per query, while it seems to use indexes.
            # Also moved the calculation field here also from another table, which greatly improves joins on Mysql.
            # see map_data for more info.

            # this query removes the double urls (see below) and makes the joins straightforward. But it's way slower.
            # In the end this would be the query we should use... but can't right now
            # sql = """SELECT MAX(map_urlrating.id) as id, map_urlrating2.calculation FROM map_urlrating
            #        INNER JOIN url ON map_urlrating.url_id = url.id
            #        INNER JOIN url_organization on url.id = url_organization.url_id
            #        INNER JOIN organization ON url_organization.organization_id = organization.id
            #        INNER JOIN map_urlrating as map_urlrating2 ON map_urlrating2.id = map_urlrating.id
            #         WHERE organization.type_id = '%(OrganizationTypeId)s'
            #         AND organization.country = '%(country)s'
            #         AND map_urlrating.`when` <= '%(when)s'
            #         GROUP BY map_urlrating.url_id
            #     """ % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
            #            "country": get_country(country)}

            # parse the query here instead of outside the function to save a second or so.
            # The ID is included for convenience of the rawquery.
            # This query will deliver double ratings for urls that are doubly listed, which is dubious.
            # this happens because multiple organizations can have the same URL.
            # It's fair that there are more issues if more organizations share the same url?

            # you also have to include a filter on reagions that are not shown on the map anymore,
            # those are mostly dead organizations... that's why this query works on map data...

            # gets all url-ratings, even on urls that are dead / not relevant at a certain time period.
            # this doesn't really work out it seems... as you dont know what url ratings are relevant when
            sql = """SELECT reporting_urlreport.id as id, reporting_urlreport.id as my_id,
                            reporting_urlreport.total_endpoints,
                            reporting_urlreport2.calculation as calculation, url.id as url_id2
                   FROM reporting_urlreport
                   INNER JOIN
                   (SELECT MAX(id) as id2 FROM reporting_urlreport or2
                   WHERE at_when <= '%(when)s' GROUP BY url_id) as x
                   ON x.id2 = reporting_urlreport.id
                   INNER JOIN url ON reporting_urlreport.url_id = url.id
                   INNER JOIN url_organization on url.id = url_organization.url_id
                   INNER JOIN organization ON url_organization.organization_id = organization.id
                   INNER JOIN reporting_urlreport as reporting_urlreport2
                        ON reporting_urlreport2.id = reporting_urlreport.id
                    WHERE organization.type_id = '%(OrganizationTypeId)s'
                    AND organization.country = '%(country)s'
                    AND reporting_urlreport.total_endpoints > 0
                    ORDER BY reporting_urlreport.url_id
                """ % {
                "when": when,
                "OrganizationTypeId": organization_type_id,
                "country": country,
            }

            # There is a cartesian product on organization, for the simple reason that organizations sometimes
            # use the same url. The filter on organization cannot be changed to left outer join, because it might
            # remove relevant organizations.... it has to be a left outer join with the  WHERE filter included then.
            # Left joining doesnt' solve it because the link of url_organization. We might get a random organization
            # for the urlrating that fits it. But there should only be one organization per urlrating? No. Because
            # url ratings are shared amongst organization. That's why it works on the map, but not here.

            # So we're doing something else: filter out the url_ratings we've already processed in the python
            # code, which is slow and ugly. But for the moment it makes sense as the query is very complicated otherwise

            # so instead use the map data as a starter and dig down from that data.

            sql = """
                    SELECT
                        map_organizationreport.id
                    FROM map_organizationreport
                    INNER JOIN


                      (SELECT stacked_organization.id as stacked_organization_id
                      FROM organization stacked_organization
                      WHERE (
                        stacked_organization.created_on <= '%(when)s'
                        AND stacked_organization.is_dead = 0
                        AND stacked_organization.type_id=%(OrganizationTypeId)s
                        AND stacked_organization.country='%(country)s'
                        )
                      OR (
                      '%(when)s' BETWEEN stacked_organization.created_on AND stacked_organization.is_dead_since
                        AND stacked_organization.is_dead = 1
                        AND stacked_organization.type_id=%(OrganizationTypeId)s
                        AND stacked_organization.country='%(country)s'
                      )) as organization_stack
                      ON organization_stack.stacked_organization_id = map_organizationreport.organization_id


                    INNER JOIN
                      organization on organization.id = stacked_organization_id
                    INNER JOIN
                      organizations_organizationtype on organizations_organizationtype.id = organization.type_id
                    INNER JOIN



                      (SELECT MAX(stacked_coordinate.id) as stacked_coordinate_id, area, geoJsonType, organization_id
                      FROM coordinate stacked_coordinate
                      INNER JOIN organization filter_organization
                        ON (stacked_coordinate.organization_id = filter_organization.id)
                      WHERE (
                        stacked_coordinate.created_on <= '%(when)s'
                        AND stacked_coordinate.is_dead = 0
                        AND filter_organization.country='%(country)s'
                        AND filter_organization.type_id=%(OrganizationTypeId)s
                        )
                      OR
                        ('%(when)s' BETWEEN stacked_coordinate.created_on AND stacked_coordinate.is_dead_since
                        AND stacked_coordinate.is_dead = 1
                        AND filter_organization.country='%(country)s'
                        AND filter_organization.type_id=%(OrganizationTypeId)s
                        ) GROUP BY calculated_area_hash, organization_id
                      ) as coordinate_stack
                      ON coordinate_stack.organization_id = map_organizationreport.organization_id


                    INNER JOIN


                      (SELECT MAX(map_organizationreport.id) as stacked_organizationrating_id
                      FROM map_organizationreport
                      INNER JOIN organization filter_organization2
                        ON (filter_organization2.id = map_organizationreport.organization_id)
                      WHERE at_when <= '%(when)s'
                      AND filter_organization2.country='%(country)s'
                      AND filter_organization2.type_id=%(OrganizationTypeId)s
                      GROUP BY organization_id
                      ) as stacked_organizationrating
                      ON stacked_organizationrating.stacked_organizationrating_id = map_organizationreport.id

                    WHERE organization.type_id = '%(OrganizationTypeId)s' AND organization.country= '%(country)s'
                    GROUP BY coordinate_stack.area, organization.name
                    ORDER BY map_organizationreport.at_when ASC
                    """ % {
                "when": when,
                "OrganizationTypeId": organization_type_id,
                "country": country,
            }

            organizationratings = OrganizationReport.objects.raw(sql)

            needed_reports = []
            for organizationrating in organizationratings:
                needed_reports.append(str(organizationrating.pk))

            reports = get_reports_by_ids(needed_reports)

            direct_reports = []
            for report in reports:
                direct_reports.append(json.loads(reports[report]))

            number_of_endpoints = 0
            number_of_urls = 0
            # log.debug(sql)

            # some urls are in multiple organizaitons, make sure that it's only shown once.
            processed_urls = []

            for direct_report in direct_reports:

                # log.debug("Processing rating of %s " %
                #     organizationrating.calculation["organization"].get("name", "UNKOWN"))

                urlratings = direct_report["organization"].get("urls", [])

                number_of_urls += len(urlratings)

                # group by vulnerability type
                for urlrating in urlratings:

                    # prevent the same urls counting double or more...
                    if urlrating["url"] in processed_urls:
                        # log.debug("Removed url because it's already in the report: %s" % urlrating["url"])
                        continue

                    processed_urls.append(urlrating["url"])

                    # log.debug("Url: %s" % (urlrating["url"]))

                    number_of_endpoints += len(urlrating["endpoints"])

                    # print(connection.queries)
                    # exit()

                    # www.kindpakket.groningen.nl is missing
                    # url reports
                    for rating in urlrating["ratings"]:

                        # log.debug("- type: %s H: %s, M: %s, L: %s" %
                        #     (rating['type'], rating['high'], rating['medium'], rating['low']))

                        if rating["type"] not in measurement:
                            measurement[rating["type"]] = {
                                "high": 0,
                                "medium": 0,
                                "low": 0,
                                "ok_urls": 0,
                                "ok_endpoints": 0,
                                "applicable_endpoints": 0,
                                "applicable_urls": 0,
                            }

                        # if rating['type'] not in scan_types:
                        scan_types.add(rating["type"])

                        measurement[rating["type"]]["high"] += rating["high"]
                        measurement[rating["type"]]["medium"] += rating["medium"]
                        measurement[rating["type"]]["low"] += rating["low"]
                        measurement[rating["type"]]["ok_urls"] += rating["ok"]
                        measurement[rating["type"]]["applicable_urls"] += 1

                        measurement["total"]["high"] += rating["high"]
                        measurement["total"]["medium"] += rating["medium"]
                        measurement["total"]["low"] += rating["low"]
                        measurement["total"]["ok_urls"] += rating["ok"]

                    # endpoint reports
                    for endpoint in urlrating["endpoints"]:

                        for rating in endpoint["ratings"]:
                            if rating["type"] not in measurement:
                                measurement[rating["type"]] = {
                                    "high": 0,
                                    "medium": 0,
                                    "low": 0,
                                    "ok_urls": 0,
                                    "ok_endpoints": 0,
                                    "applicable_endpoints": 0,
                                    "applicable_urls": 0,
                                }

                            # debugging, perhaps it appears that the latest scan is not set properly
                            # if rating['type'] == 'ftp' and rating['high']:
                            #     log.debug("High ftp added for %s" % urlrating["url"])

                            # if rating['type'] not in scan_types:
                            scan_types.add(rating["type"])

                            measurement[rating["type"]]["high"] += rating["high"]
                            measurement[rating["type"]]["medium"] += rating["medium"]
                            measurement[rating["type"]]["low"] += rating["low"]
                            measurement[rating["type"]]["ok_endpoints"] += rating["ok"]
                            measurement[rating["type"]]["applicable_endpoints"] += 1

                            measurement["total"]["high"] += rating["high"]
                            measurement["total"]["medium"] += rating["medium"]
                            measurement["total"]["low"] += rating["low"]
                            measurement["total"]["ok_endpoints"] += rating["ok"]

            # store these results per scan type, and only retrieve this per scan type...
            for scan_type in scan_types:
                # log.debug(scan_type)
                if scan_type in measurement:
                    vs = VulnerabilityStatistic()
                    vs.at_when = when
                    vs.organization_type = OrganizationType(pk=organization_type_id)
                    vs.country = country
                    vs.scan_type = scan_type
                    vs.high = measurement[scan_type]["high"]
                    vs.medium = measurement[scan_type]["medium"]
                    vs.low = measurement[scan_type]["low"]
                    vs.ok_urls = measurement[scan_type]["ok_urls"]
                    vs.ok_endpoints = measurement[scan_type]["ok_endpoints"]

                    if scan_type in PUBLISHED_SCAN_TYPES:
                        vs.urls = measurement[scan_type]["applicable_urls"]
                        vs.endpoints = measurement[scan_type]["applicable_endpoints"]
                    else:
                        # total
                        vs.urls = number_of_urls
                        vs.endpoints = number_of_endpoints

                    if scan_type in ENDPOINT_SCAN_TYPES:
                        vs.ok = measurement[scan_type]["ok_endpoints"]
                    elif scan_type in URL_SCAN_TYPES:
                        vs.ok = measurement[scan_type]["ok_urls"]
                    else:
                        # total: everything together.
                        vs.ok = measurement[scan_type]["ok_urls"] + measurement[scan_type]["ok_endpoints"]

                    vs.save()


@app.task(queue="reporting")
def calculate_map_data_today():
    calculate_map_data.si(1).apply_async()


@app.task(queue="reporting")
def calculate_map_data(days: int = 366, countries: List = None, organization_types: List = None):
    from django.db import OperationalError

    log.info("calculate_map_data")

    map_configurations = filter_map_configs(countries=countries, organization_types=organization_types)

    # the "all" filter will retrieve all layers at once
    scan_types = ["all"] + PUBLISHED_SCAN_TYPES

    for map_configuration in map_configurations:
        for days_back in list(reversed(range(0, days))):
            when = datetime.now(pytz.utc) - timedelta(days=days_back)
            for scan_type in scan_types:

                # You can expect something to change each day. Therefore just store the map data each day.
                MapDataCache.objects.all().filter(
                    at_when=when,
                    country=map_configuration["country"],
                    organization_type=OrganizationType(pk=map_configuration["organization_type"]),
                    filters=[scan_type],
                ).delete()

                log.debug(
                    "Country: %s, Organization_type: %s, day: %s, date: %s, filter: %s"
                    % (
                        map_configuration["country"],
                        map_configuration["organization_type__name"],
                        days_back,
                        when,
                        scan_type,
                    )
                )
                data = get_map_data(
                    map_configuration["country"], map_configuration["organization_type__name"], days_back, scan_type
                )

                try:
                    cached = MapDataCache()
                    cached.organization_type = OrganizationType(pk=map_configuration["organization_type"])
                    cached.country = map_configuration["country"]
                    cached.filters = [scan_type]
                    cached.at_when = when
                    cached.dataset = data
                    cached.save()
                except OperationalError as a:
                    # The public user does not have permission to run insert statements....
                    log.exception(a)


@app.task(queue="reporting")
def calculate_high_level_stats(days: int = 1, countries: List = None, organization_types: List = None):
    log.info("Creating high_level_stats")

    map_configurations = filter_map_configs(countries=countries, organization_types=organization_types)

    for map_configuration in map_configurations:
        for days_back in list(reversed(range(0, days))):
            log.debug(
                "For country: %s type: %s days back: %s"
                % (map_configuration["country"], map_configuration["organization_type__name"], days_back)
            )

            when = datetime.now(pytz.utc) - timedelta(days=days_back)

            # prevent double high level stats
            HighLevelStatistic.objects.all().filter(
                at_when=when,
                country=map_configuration["country"],
                organization_type=OrganizationType(pk=map_configuration["organization_type__id"]),
            ).delete()

            measurement = {
                "high": 0,
                "medium": 0,
                "good": 0,
                "total_organizations": 0,
                "total_score": 0,
                "no_rating": 0,
                "total_urls": 0,
                "high_urls": 0,
                "medium_urls": 0,
                "good_urls": 0,
                "included_organizations": 0,
                "endpoints": 0,
                "endpoint": OrderedDict(),
                "explained": {},
            }

            sql = """
                SELECT
                    map_organizationreport.id,
                    map_organizationreport.medium,
                    map_organizationreport.high,
                    map_organizationreport.total_urls
                FROM
                    map_organizationreport
                INNER JOIN
                    (
                    SELECT MAX(or2.id) as id2
                    FROM map_organizationreport or2
                    INNER JOIN organization as filter_organization
                    ON (filter_organization.id = or2.organization_id)
                    WHERE
                        at_when <= '%(when)s'
                        AND filter_organization.country='%(country)s'
                        AND filter_organization.type_id=%(OrganizationTypeId)s
                   GROUP BY organization_id
                ) as stacked_organizationreport
                ON stacked_organizationreport.id2 = map_organizationreport.id
                INNER JOIN organization ON map_organizationreport.organization_id = organization.id
                WHERE
                    /* Only include organizations that are alive now... */
                    (('%(when)s' BETWEEN organization.created_on AND organization.is_dead_since
                    AND organization.is_dead = 1
                    ) OR (
                    organization.created_on <= '%(when)s'
                    AND organization.is_dead = 0
                    ))
                    AND organization.type_id = '%(OrganizationTypeId)s'
                    AND organization.country = '%(country)s'
                    /* Remove organizations with zero urls, otherwise they would be good or bad automatically. */
                    AND total_urls > 0
            """ % {
                "when": when,
                "OrganizationTypeId": map_configuration["organization_type__id"],
                "country": map_configuration["country"],
            }

            # log.debug(sql)

            ratings = OrganizationReport.objects.raw(sql)

            needed_reports = []
            for organizationrating in ratings:
                needed_reports.append(str(organizationrating.id))

            reports = get_reports_by_ids(needed_reports)

            noduplicates = []
            for rating in ratings:

                measurement["total_organizations"] += 1

                if rating.high:
                    measurement["high"] += 1
                elif rating.medium:
                    measurement["medium"] += 1
                    # low does not impact any score.
                else:
                    measurement["good"] += 1

                # count the urls, from the latest rating. Which is very dirty :)
                # it will double the urls that are shared between organizations.
                # that is not really bad, it distorts a little.
                # we're forced to load each item separately anyway, so why not read it?
                calculation = json.loads(reports[rating.id])
                measurement["total_urls"] += len(calculation["organization"]["urls"])

                measurement["good_urls"] += sum(
                    [lx["high"] == 0 and lx["medium"] == 0 for lx in calculation["organization"]["urls"]]
                )
                measurement["medium_urls"] += sum(
                    [lx["high"] == 0 and lx["medium"] > 0 for lx in calculation["organization"]["urls"]]
                )
                measurement["high_urls"] += sum([lx["high"] > 0 for lx in calculation["organization"]["urls"]])

                measurement["included_organizations"] += 1

                # make some generic stats for endpoints
                for url in calculation["organization"]["urls"]:
                    if url["url"] in noduplicates:
                        continue
                    noduplicates.append(url["url"])

                    # endpoints

                    # only add this to the first output, otherwise you have to make this a graph.
                    # it's simply too much numbers to make sense anymore.
                    # yet there is not enough data to really make a graph.
                    # do not have duplicate urls in the stats.
                    # ratings
                    for r in url["ratings"]:
                        # stats over all different ratings
                        if r["type"] not in measurement["explained"]:
                            measurement["explained"][r["type"]] = {}
                            measurement["explained"][r["type"]]["total"] = 0
                        if not r["explanation"].startswith("Repeated finding."):
                            if r["explanation"] not in measurement["explained"][r["type"]]:
                                measurement["explained"][r["type"]][r["explanation"]] = 0

                            measurement["explained"][r["type"]][r["explanation"]] += 1
                            measurement["explained"][r["type"]]["total"] += 1

                    for endpoint in url["endpoints"]:

                        # Only add the endpoint once for a series of ratings. And only if the
                        # ratings is not a repeated finding.
                        added_endpoint = False

                        for r in endpoint["ratings"]:
                            # stats over all different ratings
                            if r["type"] not in measurement["explained"]:
                                measurement["explained"][r["type"]] = {}
                                measurement["explained"][r["type"]]["total"] = 0
                            if not r["explanation"].startswith("Repeated finding."):
                                if r["explanation"] not in measurement["explained"][r["type"]]:
                                    measurement["explained"][r["type"]][r["explanation"]] = 0

                                measurement["explained"][r["type"]][r["explanation"]] += 1
                                measurement["explained"][r["type"]]["total"] += 1

                                # stats over all endpoints
                                # duplicates skew these stats.
                                # it is possible to have multiple endpoints of the same type
                                # while you can have multiple ipv4 and ipv6, you can only reach one
                                # therefore reduce this to have only one v4 and v6
                                if not added_endpoint:
                                    added_endpoint = True
                                    endpointtype = "%s/%s (%s)" % (
                                        endpoint["protocol"],
                                        endpoint["port"],
                                        ("IPv4" if endpoint["ip_version"] == 4 else "IPv6"),
                                    )
                                    if endpointtype not in measurement["endpoint"]:
                                        measurement["endpoint"][endpointtype] = {
                                            "amount": 0,
                                            "port": endpoint["port"],
                                            "protocol": endpoint["protocol"],
                                            "ip_version": endpoint["ip_version"],
                                        }
                                    measurement["endpoint"][endpointtype]["amount"] += 1
                                    measurement["endpoints"] += 1

            """                 measurement["total_organizations"] += 1
                                measurement["total_score"] += 0
                                measurement["no_rating"] += 1
            """
            measurement["endpoint"] = sorted(measurement["endpoint"].items())

            if measurement["included_organizations"]:
                measurement["high percentage"] = round(
                    (measurement["high"] / measurement["included_organizations"]) * 100
                )
                measurement["medium percentage"] = round(
                    (measurement["medium"] / measurement["included_organizations"]) * 100
                )
                measurement["good percentage"] = round(
                    (measurement["good"] / measurement["included_organizations"]) * 100
                )
            else:
                measurement["high percentage"] = 0
                measurement["medium percentage"] = 0
                measurement["good percentage"] = 0

            if measurement["total_urls"]:
                measurement["high url percentage"] = round((measurement["high_urls"] / measurement["total_urls"]) * 100)
                measurement["medium url percentage"] = round(
                    (measurement["medium_urls"] / measurement["total_urls"]) * 100
                )
                measurement["good url percentage"] = round((measurement["good_urls"] / measurement["total_urls"]) * 100)
            else:
                measurement["high url percentage"] = 0
                measurement["medium url percentage"] = 0
                measurement["good url percentage"] = 0

            s = HighLevelStatistic()
            s.country = map_configuration["country"]
            s.organization_type = OrganizationType.objects.get(name=map_configuration["organization_type__name"])
            s.at_when = when
            s.report = measurement
            s.save()


def create_organization_report_on_moment(organization: Organization, when: datetime = None):
    """
    # also callable as admin action
    # this is 100% based on url ratings, just an aggregate of the last status.
    # make sure the URL ratings are up to date, they will check endpoints and such.

    :param organization:
    :param when:
    :return:
    """
    # If there is no time slicing, then it's today.
    if not when:
        when = datetime.now(pytz.utc)

    log.info(
        "Creating report for %s on %s"
        % (
            organization,
            when,
        )
    )

    # if there already is an organization rating on this moment, skip it. You should have deleted it first.
    # this is probably a lot quicker than calculating the score and then deepdiffing it.
    # using this check we can also ditch deepdiff, because ratings on the same day are always the same.
    # todo: we should be able to continue on a certain day.
    if OrganizationReport.objects.all().filter(organization=organization, at_when=when).exists():
        log.info("Rating already exists for %s on %s. Not overwriting." % (organization, when))

    # Done: closing off urls, after no relevant endpoints, but still resolvable. Done.
    # if so, we don't need to check for existing endpoints anymore at a certain time...
    # It seems we don't need the url object, only a flat list of pk's for urlratigns.
    # urls = relevant_urls_at_timepoint(organizations=[organization], when=when)
    urls = relevant_urls_at_timepoint_organization(organization=organization, when=when)

    # Here used to be a lost of nested queries: getting the "last" one per url. This has been replaced with a
    # custom query that is many many times faster.
    all_url_ratings = get_latest_urlratings_fast(urls, when)
    scores = aggegrate_url_rating_scores(all_url_ratings)

    # Still do deepdiff to prevent double reports.
    try:
        last = OrganizationReport.objects.filter(organization=organization, at_when__lte=when).latest("at_when")
    except OrganizationReport.DoesNotExist:
        log.debug("Could not find the last organization rating, creating a dummy one.")
        last = OrganizationReport()  # create an empty one

    scores["name"] = organization.name
    calculation = {"organization": scores}

    # this is 10% faster without deepdiff, the major pain is elsewhere.
    if DeepDiff(last.calculation, calculation, ignore_order=True, report_repetition=True):
        log.info("The calculation for %s on %s has changed, so we're saving this rating." % (organization, when))

        # remove urls and name from scores object, so it can be used as initialization parameters (saves lines)
        # this is by reference, meaning that the calculation will be affected if we don't work on a clone.
        init_scores = deepcopy(scores)
        del init_scores["name"]
        del init_scores["urls"]

        organizationrating = OrganizationReport(**init_scores)
        organizationrating.organization = organization
        organizationrating.at_when = when
        organizationrating.calculation = calculation

        organizationrating.save()
        log.info("Saved report for %s on %s." % (organization, when))
    else:
        # This happens because some urls are dead etc: our filtering already removes this from the relevant information
        # at this point in time. But since it's still a significant moment, it will just show that nothing has changed.
        log.warning("The calculation for %s on %s is the same as the previous one. Not saving." % (organization, when))


def relevant_urls_at_timepoint_organization(organization: Organization, when: datetime):
    # doing this, without the flat list results in about 40% faster execution, most notabily on large organizations
    # if you want to see what's going on, see relevant_urls_at_timepoint
    # removed the IN query to gain some extra speed
    # returned a flat list of pk's, since we don't do anything else with these urls. It's not particulary faster.
    queryset = Url.objects.filter(organization=organization)
    return relevant_urls_at_timepoint(queryset, when)


@app.task(queue="reporting")
def default_organization_rating(organizations: List[int]):
    """
    Generate default ratings so all organizations are on the map (as being grey). This prevents
    empty spots / holes.
    :return:
    """

    if not organizations:
        organizations = list(Organization.objects.all().values_list("id", flat=True))

    for organization_id in organizations:

        organization = Organization.objects.all().filter(id=organization_id).first()
        if not organization:
            continue

        log.info("Giving organization a default rating: %s" % organization)

        when = organization.created_on if organization.created_on else START_DATE

        r = OrganizationReport()
        r.at_when = when
        r.organization = organization
        r.calculation = {
            "organization": {
                "name": organization.name,
                "high": 0,
                "medium": 0,
                "low": 0,
                "ok": 0,
                "total_urls": 0,
                "high_urls": 0,
                "medium_urls": 0,
                "low_urls": 0,
                "ok_urls": 0,
                "explained_high": 0,
                "explained_medium": 0,
                "explained_low": 0,
                "explained_high_endpoints": 0,
                "explained_medium_endpoints": 0,
                "explained_low_endpoints": 0,
                "explained_high_urls": 0,
                "explained_medium_urls": 0,
                "explained_low_urls": 0,
                "explained_total_url_issues": 0,
                "explained_url_issues_high": 0,
                "explained_url_issues_medium": 0,
                "explained_url_issues_low": 0,
                "explained_total_endpoint_issues": 0,
                "explained_endpoint_issues_high": 0,
                "explained_endpoint_issues_medium": 0,
                "explained_endpoint_issues_low": 0,
                "total_endpoints": 0,
                "high_endpoints": 0,
                "medium_endpoints": 0,
                "low_endpoints": 0,
                "ok_endpoints": 0,
                "total_url_issues": 0,
                "total_endpoint_issues": 0,
                "url_issues_high": 0,
                "url_issues_medium": 0,
                "url_issues_low": 0,
                "endpoint_issues_high": 0,
                "endpoint_issues_medium": 0,
                "endpoint_issues_low": 0,
                "urls": [],
                "total_issues": 0,
            }
        }
        r.save()


@app.task(queue="reporting")
def create_organization_reports_now(organizations: List[int]):

    for organization_id in organizations:
        organization = Organization.objects.all().filter(id=organization_id).first()
        if not organization:
            continue

        now = datetime.now(pytz.utc)
        create_organization_report_on_moment(organization, now)


@app.task(queue="reporting")
def recreate_organization_reports(organizations: List[int]):
    """Remove organization rating and rebuild a new."""

    # todo: only for allowed organizations...

    for organization_id in organizations:
        organization = Organization.objects.all().filter(id=organization_id).first()
        if not organization:
            continue

        log.info("Adding rating for organization %s", organization)

        # Given this is a rebuild, delete all previous reports;
        OrganizationReport.objects.all().filter(organization=organization).delete()

        # and then rebuild the ratings per moment, which is a maximum of one per day.
        urls = Url.objects.filter(organization__in=organizations)
        moments, happenings = significant_moments(urls=urls, reported_scan_types=get_allowed_to_report())

        moments = reduce_to_save_data(moments)
        for moment in moments:
            create_organization_report_on_moment(organization, moment)

        # If there is nothing to show, use a fallback value to display "something" on the map.
        # We cannot add default ratings per organizations per-se, as they would intefear with the timeline.
        # for example: if an organization in 2018 is a merge of organizations in 2017, it will mean that on
        # january first 2018, there would be an empty and perfect rating. That would show up on the map as
        # empty which does not make sense. Therefore we only add a default rating if there is really nothing else.
        if not moments:
            # Make sure the organization has the default rating
            default_organization_rating(organizations=[organization.pk])


def reduce_to_save_data(moments: List[datetime]) -> List[datetime]:

    # reduce to only the dates, easier to work with.
    moments = reduce_to_days(moments)

    results = []
    # get the days in this year:
    some_day_a_year_ago = datetime.now(pytz.utc) - timedelta(days=365)
    some_day_a_two_years_ago = datetime.now(pytz.utc) - timedelta(days=730)

    to_reduce_to_days = [moment for moment in moments if moment > some_day_a_year_ago]
    # log.debug(f"To days: {to_reduce_to_days}")
    results += reduce_to_days(to_reduce_to_days)

    to_reduce_to_weeks = [
        moment
        for moment in moments
        if
        # not simplyfying the chain expression, as i can't understand what is being said clear enough
        moment > some_day_a_two_years_ago and moment <= some_day_a_year_ago
    ]
    # log.debug(f"To weeks: {to_reduce_to_weeks}")
    results += reduce_to_weeks(to_reduce_to_weeks)

    to_reduce_to_months = [moment for moment in moments if moment <= some_day_a_two_years_ago]
    # log.debug(f"To months: {to_reduce_to_weeks}")
    results += reduce_to_months(to_reduce_to_months)

    # make sure the last possible moment is chosen on these moments:
    return set_dates_to_last_possible_moment(results)


def reduce_to_months(moments: List[datetime]) -> List[datetime]:
    reduced_datetimes: List[datetime] = []

    # last moment of the month is good enough, that is at least a point there will be data.
    # https://stackoverflow.com/questions/42950/how-to-get-the-last-day-of-the-month
    for moment in moments:
        (first_weekday, amount_of_days_in_month) = calendar.monthrange(moment.year, moment.month)
        if datetime(moment.year, moment.month, amount_of_days_in_month, tzinfo=pytz.utc) not in reduced_datetimes:
            reduced_datetimes.append(datetime(moment.year, moment.month, amount_of_days_in_month, tzinfo=pytz.utc))

    return reduced_datetimes


def reduce_to_weeks(moments: List[datetime]) -> List[datetime]:
    reduced_datetimes: List[datetime] = []
    processed_weeks_and_years: List[Tuple[int, int]] = []

    for moment in moments:
        # https://stackoverflow.com/questions/2600775/how-to-get-week-number-in-python
        week = moment.isocalendar()[1]
        if (week, moment.year) not in processed_weeks_and_years:
            processed_weeks_and_years.append((week, moment.year))
            reduced_datetimes.append(datetime_to_last_day_of_the_week(moment))

    return reduced_datetimes


def datetime_to_last_day_of_the_week(some_datetime: datetime) -> datetime:
    # https://stackoverflow.com/questions/9847213/how-do-i-get-the-day-of-week-given-a-date
    weekday = some_datetime.weekday()
    if weekday < 7:
        add_days = 7 - weekday  # 7 - 4 = 3
        return some_datetime + timedelta(days=add_days)

    return some_datetime


def reduce_to_days(moments: List[datetime]) -> List[datetime]:
    # reduce to only the dates.
    reduced_datetimes: List[date] = list(set([moment.date() for moment in moments]))

    # pick the first possible moment on the date:
    as_datetimes = [
        datetime(year=moment.year, month=moment.month, day=moment.day, tzinfo=pytz.utc) for moment in reduced_datetimes
    ]

    return as_datetimes


def set_dates_to_last_possible_moment(moments: List[datetime]) -> List[datetime]:
    new_moments = []
    for moment in moments:
        new_moments.append(datetime(moment.year, moment.month, moment.day, 23, 59, 59, 999999, tzinfo=pytz.utc))

    return new_moments


@app.task(queue="reporting")
def update_report_tasks(url_chunk: List[int]):
    """
    A small update function that only rebuilds a single url and the organization report for a single day. Using this
    during onboarding, it's possible to show changes much faster than a complete rebuild.

    :param url_chunk: List of urls
    :return:
    """
    tasks = []

    for url_id in url_chunk:
        url = Url.objects.all().filter(id=url_id).first()
        if not url:
            continue

        organizations = [o.pk for o in list(url.organization.all())]

        # Note that you cannot determine the moment to be "now" as the urls have to be re-reated.
        # the moment to rerate organizations is when the url_ratings has finished.

        tasks.append(recreate_url_reports.si([url]) | create_organization_reports_now.si(organizations))

        # Calculating statistics is _extremely slow_ so we're not doing that in this method to keep the pace.
        # Otherwise you'd have a 1000 statistic rebuilds pending, all doing a marginal job.
        # calculate_vulnerability_statistics.si(1) | calculate_map_data.si(1)

    return group(tasks)

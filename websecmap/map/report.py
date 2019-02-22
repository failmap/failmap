import logging
from datetime import datetime, timedelta
from typing import List

import pytz
from celery import group

from websecmap.celery import Task, app
from websecmap.map.models import Configuration, MapDataCache, VulnerabilityStatistic
from websecmap.map.views import get_map_data
from websecmap.organizations.models import Organization, OrganizationType, Url
from websecmap.reporting.models import OrganizationReport
from websecmap.reporting.report import (create_organization_reports_now,
                                        default_organization_rating, recreate_url_reports)
from websecmap.scanners.scanner.scanner import q_configurations_to_report
from websecmap.scanners.types import ALL_SCAN_TYPES

log = logging.getLogger(__package__)


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """
    Compose taskset to rebuild specified organizations/urls.
    """

    if endpoints_filter:
        raise NotImplementedError('This scanner does not work on a endpoint level.')

    log.info("Organization filter: %s" % organizations_filter)
    log.info("Url filter: %s" % urls_filter)

    # Only displayed configurations are reported. Because why have reports on things you don't display?
    # apply filter to organizations (or if no filter, all organizations)
    organizations = Organization.objects.filter(q_configurations_to_report('organization'), **organizations_filter)

    log.debug("Organizations: %s" % len(organizations))

    # Create tasks for rebuilding ratings for selected organizations and urls.
    # Wheneven a url has been (re)rated the organization for that url need to
    # be (re)rated as well to propagate the result of the url rate. Tasks will
    # be created per organization to first rebuild all of this organizations
    # urls (depending on url filters) after which the organization rating will
    # be rebuild.

    tasks = []

    for organization in organizations:
        urls = Url.objects.filter(q_configurations_to_report(), organization=organization, **urls_filter)
        if not urls:
            # can still add an empty organization rating even though there is nothing to show. Will create an
            # empty gray region.
            tasks.append(default_organization_rating.si([organization]))
            continue

        # make sure default organization rating is in place
        tasks.append(recreate_url_reports.si(urls)
                     | create_organization_reports_now.si([organization]))

    if not tasks:
        log.error("Could not rebuild reports, filters resulted in no tasks created.")
        log.debug("Organization filter: %s" % organizations_filter)
        log.debug("Url filter: %s" % urls_filter)
        log.debug("urls to display: %s" % q_configurations_to_report())
        log.debug("organizatins to display: %s" % q_configurations_to_report('organization'))
        return group()

    # when trying to report on a specific url or organization (so not everything) also don't rebuild all caches
    # from the past. This saves a lot of rebuild time, making results visible in a "fixing state" and the entire rebuild
    # will happen at a scheduled interval to make sure the rest is up to date.
    if organizations_filter or urls_filter:
        days = 2
    else:
        # no, you always want to have a pretty quick update. If you want to revise the entire dataset, you might
        # have adjusted the value of the ratings somewhere. Then that would be a special operation to recalculate
        # the entire database. So this can just be two days as well.
        days = 2

    log.debug("Number of tasks: %s" % len(tasks))

    # finally, rebuild the graphs (which can mis-matchi a bit if the last reports aren't in yet. Will have to do for now
    # mainly as we're trying to get away from canvas and it's buggyness.

    if organizations_filter.get('country__in', None):
        tasks.append(calculate_vulnerability_statistics.si(1, organizations_filter['country__in']))
        tasks.append(calculate_map_data.si(1, organizations_filter['country__in']))
    elif organizations_filter.get('country', None):
        tasks.append(calculate_vulnerability_statistics.si(1, [organizations_filter['country']]))
        tasks.append(calculate_map_data.si(1, [organizations_filter['country']]))
    else:
        # 2 days if you have altered stuff a day before etc...
        tasks.append(calculate_vulnerability_statistics.si(days))
        tasks.append(calculate_map_data.si(days))

    task = group(tasks)

    return task


@app.task(queue='storage')
def calculate_vulnerability_statistics(days: int = 366, country: List[str] = []):
    log.info("Calculation vulnerability graphs")

    # for everything that is displayed on the site:
    if country:
        # if you have a country, (or other filter) you don't care about the default filter.
        map_configurations = Configuration.objects.all().filter(country__in=country)
    else:
        map_configurations = Configuration.objects.all().filter(is_displayed=True)

    map_configurations = map_configurations.order_by('display_order').values('country', 'organization_type')

    for map_configuration in map_configurations:
        scan_types = set()  # set instead of list to prevent checking if something is in there already.
        scan_types.add('total')  # the total would be separated per char if directly passed into set()
        scan_types.add('ftp')
        organization_type_id = map_configuration['organization_type']
        country = map_configuration['country']

        # for the entire year, starting with oldest (in case the other tasks are not ready)
        for days_back in list(reversed(range(0, days))):
            measurement = {'total': {'high': 0, 'medium': 0, 'low': 0}}
            when = datetime.now(pytz.utc) - timedelta(days=days_back)
            log.info("Days back:%s Date: %s" % (days_back, when))

            # delete this specific moment as it's going to be replaced, so it's not really noticable an update is
            # taking place.
            VulnerabilityStatistic.objects.all().filter(
                when=when, country=country, organization_type=OrganizationType(pk=organization_type_id)).delete()

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
                   WHERE `when` <= '%(when)s' GROUP BY url_id) as x
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
                """ % {"when": when, "OrganizationTypeId": organization_type_id, "country": country}

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
                        organization.name,
                        organizations_organizationtype.name,
                        coordinate_stack.area,
                        coordinate_stack.geoJsonType,
                        organization.id,
                        or3.calculation,
                        reporting_organizationreport.high,
                        reporting_organizationreport.medium,
                        reporting_organizationreport.low,
                        reporting_organizationreport.total_issues,
                        reporting_organizationreport.total_urls,
                        reporting_organizationreport.high_urls,
                        reporting_organizationreport.medium_urls,
                        reporting_organizationreport.low_urls
                    FROM reporting_organizationreport
                    INNER JOIN
                      (SELECT id as stacked_organization_id
                      FROM organization stacked_organization
                      WHERE (stacked_organization.created_on <= '%(when)s' AND stacked_organization.is_dead = 0)
                      OR (
                      '%(when)s' BETWEEN stacked_organization.created_on AND stacked_organization.is_dead_since
                      AND stacked_organization.is_dead = 1)) as organization_stack
                      ON organization_stack.stacked_organization_id = reporting_organizationreport.organization_id
                    INNER JOIN
                      organization on organization.id = stacked_organization_id
                    INNER JOIN
                      organizations_organizationtype on organizations_organizationtype.id = organization.type_id
                    INNER JOIN
                      (SELECT MAX(id) as stacked_coordinate_id, area, geoJsonType, organization_id
                      FROM coordinate stacked_coordinate
                      WHERE (stacked_coordinate.created_on <= '%(when)s' AND stacked_coordinate.is_dead = 0)
                      OR
                      ('%(when)s' BETWEEN stacked_coordinate.created_on AND stacked_coordinate.is_dead_since
                      AND stacked_coordinate.is_dead = 1) GROUP BY area, organization_id) as coordinate_stack
                      ON coordinate_stack.organization_id = reporting_organizationreport.organization_id
                    INNER JOIN
                      (SELECT MAX(id) as stacked_organizationrating_id FROM reporting_organizationreport
                      WHERE `when` <= '%(when)s' GROUP BY organization_id) as stacked_organizationrating
                      ON stacked_organizationrating.stacked_organizationrating_id = reporting_organizationreport.id
                    INNER JOIN reporting_organizationreport as or3 ON or3.id = reporting_organizationreport.id
                    WHERE organization.type_id = '%(OrganizationTypeId)s' AND organization.country= '%(country)s'
                    GROUP BY coordinate_stack.area, organization.name
                    ORDER BY reporting_organizationreport.`when` ASC
                    """ % {"when": when, "OrganizationTypeId": organization_type_id,
                           "country": country}

            organizationratings = OrganizationReport.objects.raw(sql)
            number_of_endpoints = 0
            number_of_urls = 0
            # log.debug(sql)

            log.info("Nr of urlratings: %s" % len(list(organizationratings)))

            # some urls are in multiple organizaitons, make sure that it's only shown once.
            processed_urls = []

            for organizationrating in organizationratings:

                # log.debug("Processing rating of %s " %
                #     organizationrating.calculation["organization"].get("name", "UNKOWN"))

                urlratings = organizationrating.calculation["organization"].get("urls", [])

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
                    for rating in urlrating['ratings']:

                        # log.debug("- type: %s H: %s, M: %s, L: %s" %
                        #     (rating['type'], rating['high'], rating['medium'], rating['low']))

                        if rating['type'] not in measurement:
                            measurement[rating['type']] = {'high': 0, 'medium': 0, 'low': 0}

                        # if rating['type'] not in scan_types:
                        scan_types.add(rating['type'])

                        measurement[rating['type']]['high'] += rating['high']
                        measurement[rating['type']]['medium'] += rating['medium']
                        measurement[rating['type']]['low'] += rating['low']

                        measurement['total']['high'] += rating['high']
                        measurement['total']['medium'] += rating['medium']
                        measurement['total']['low'] += rating['low']

                    # endpoint reports
                    for endpoint in urlrating['endpoints']:

                        for rating in endpoint['ratings']:
                            if rating['type'] not in measurement:
                                measurement[rating['type']] = {'high': 0, 'medium': 0, 'low': 0}

                            # debugging, perhaps it appears that the latest scan is not set properly
                            # if rating['type'] == 'ftp' and rating['high']:
                            #     log.debug("High ftp added for %s" % urlrating["url"])

                            # if rating['type'] not in scan_types:
                            scan_types.add(rating['type'])

                            measurement[rating['type']]['high'] += rating['high']
                            measurement[rating['type']]['medium'] += rating['medium']
                            measurement[rating['type']]['low'] += rating['low']

                            measurement['total']['high'] += rating['high']
                            measurement['total']['medium'] += rating['medium']
                            measurement['total']['low'] += rating['low']

            # store these results per scan type, and only retrieve this per scan type...
            for scan_type in scan_types:
                # log.debug(scan_type)
                if scan_type in measurement:
                    vs = VulnerabilityStatistic()
                    vs.when = when
                    vs.organization_type = OrganizationType(pk=organization_type_id)
                    vs.country = country
                    vs.scan_type = scan_type
                    vs.high = measurement[scan_type]['high']
                    vs.medium = measurement[scan_type]['medium']
                    vs.low = measurement[scan_type]['low']
                    vs.urls = number_of_urls
                    vs.endpoints = number_of_endpoints
                    vs.save()


@app.task(queue='storage')
def calculate_map_data_today():
    calculate_map_data.si(1).apply_async()


@app.task(queue='storage')
def calculate_map_data(days: int = 366, country: List[str] = []):
    from django.db import OperationalError

    log.info("calculate_map_data")

    if country:
        # if you have a country, (or other filter) you don't care about the default filter.
        map_configurations = Configuration.objects.all().filter(country__in=country)
    else:
        map_configurations = Configuration.objects.all().filter(is_displayed=True)

    map_configurations = map_configurations.order_by('display_order').values(
        'country', 'organization_type__name', 'organization_type')

    # the "all" filter will retrieve all layers at once
    scan_types = ALL_SCAN_TYPES + ["all"]

    for map_configuration in map_configurations:
        for days_back in list(reversed(range(0, days))):
            when = datetime.now(pytz.utc) - timedelta(days=days_back)
            for scan_type in scan_types:

                # You can expect something to change each day. Therefore just store the map data each day.
                MapDataCache.objects.all().filter(
                    when=when, country=map_configuration['country'],
                    organization_type=OrganizationType(pk=map_configuration['organization_type']),
                    filters=[scan_type]
                ).delete()

                log.debug("Country: %s, Organization_type: %s, day: %s, date: %s, filter: %s" % (
                    map_configuration['country'], map_configuration['organization_type__name'],
                    days_back, when, scan_type
                ))
                data = get_map_data(
                    map_configuration['country'],
                    map_configuration['organization_type__name'],
                    days_back,
                    scan_type
                )

                try:
                    cached = MapDataCache()
                    cached.organization_type = OrganizationType(pk=map_configuration['organization_type'])
                    cached.country = map_configuration['country']
                    cached.filters = [scan_type]
                    cached.when = when
                    cached.dataset = data
                    cached.save()
                except OperationalError as a:
                    # The public user does not have permission to run insert statements....
                    log.exception(a)

import calendar
import logging
from collections import OrderedDict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import List, Tuple

from celery import group
from django.db.models import Count
from django.db import OperationalError

from websecmap.celery import Task, app
from websecmap.map.logic.map import get_map_data, get_reports_by_ids
from websecmap.map.map_configs import filter_map_configs
from websecmap.map.models import HighLevelStatistic, MapDataCache, OrganizationReport, VulnerabilityStatistic
from websecmap.map.util import transparent_json_to_zip_storage
from websecmap.organizations.models import Organization, OrganizationType, Url
from websecmap.reporting.diskreport import store_report
from websecmap.reporting.report import (
    START_DATE,
    aggegrate_url_rating_scores,
    get_latest_urlratings_fast,
    recreate_url_reports,
    relevant_urls_at_timepoint,
    significant_moments,
)
from websecmap.scanners import init_dict
from websecmap.scanners.scanmetadata import get_backend_scanmetadata
from websecmap.scanners.scanner.__init__ import q_configurations_to_report

log = logging.getLogger(__package__)


def compose_task(
    organizations_filter: dict = None,
    urls_filter: dict = None,
    endpoints_filter: dict = None,
) -> Task:
    """
    Compose taskset to rebuild specified organizations/urls.
    """
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)

    if endpoints_filter:
        raise NotImplementedError("This scanner does not work on a endpoint level.")

    log.info("Organization filter: %s", organizations_filter)
    log.info("Url filter: %s", urls_filter)

    # Only displayed configurations are reported. Because why have reports on things you don't display?
    # apply filter to organizations (or if no filter, all organizations)
    organization_ids = Organization.objects.filter(
        q_configurations_to_report("organization"),
        # don't report over dead organizations as results will always be the same....
        is_dead=False,
        **organizations_filter,
    ).values_list("id", flat=True)

    # make sure they are unique
    organization_ids = list(set(organization_ids))

    log.debug("Organizations: %s", len(organization_ids))

    # Create tasks for rebuilding ratings for selected organizations and urls.
    # Wheneven a url has been (re)rated the organization for that url need to
    # be (re)rated as well to propagate the result of the url rate. Tasks will
    # be created per organization to first rebuild all of this organizations
    # urls (depending on url filters) after which the organization rating will
    # be rebuild.

    # prevent that for every organization the same urls are being re-rated. Just rate the URL once instead of
    # per organization...

    # first uniquely get all urls for all these organizations, in batches of 1000 organizations due to
    # limitations of the _IN  -> or just keep it stupid...
    tasks = []

    urls = (
        Url.objects.filter(
            q_configurations_to_report(),
            organization__in=organization_ids,
            **urls_filter
            # To save time, only acccept urls that have at least one endpoint.
            # which is wrong, since there could be only url ratings, and it's extremely rare?
            # : also include deleted urls, so to stabilize reporting over time
        )
        .annotate(n_endpoints=Count("endpoint"))
        .filter(n_endpoints__gt=0)
        .only("id", "organization__id")
        .values("id", "organization__id")
    )

    # just once for every url
    url_ids = {url["id"] for url in urls}
    tasks.extend(recreate_url_reports(list(url_ids)))

    # todo: is the order right? so first url reports and then the organization reports?
    # this is placed in one task each to run simultaneously instead of sequentially in a for loop

    # add dummy tasks that serve as a buffer between url reports and organization reports.
    # dummy tasks should last as long as the longest url rating and there should be enough dummies
    # to keep all workers busy and presto: all url reports are finished before org reports are made without
    # the giant memory overhead on each task. This sort of works because url reports are pretty small tasks :D
    # -> currently split up in two tasks... so the dummy has been removed.

    # creating organization reports is now placed in report_organization, so they can be scheduled at a different time.
    # this gives a bit more control on what tasks are added to the queue at what point.

    if not tasks:
        log.warning("Could not rebuild reports, filters resulted in no tasks created.")
        log.debug("Organization filter: %s, Url filter: %s", organizations_filter, urls_filter)
        log.debug(
            "urls to display: %s, organizations, to display: %s",
            q_configurations_to_report(),
            q_configurations_to_report("organization"),
        )
        return group()

    log.debug("Number of tasks: %s", len(tasks))

    # after this prepare caches should be fired. BUT don't chain that task as it will be added to the memory
    # of each of the above created tasks: this causes a factor of 100 memory increase (as every of the subtasks
    # is added to the body of the message on queue!).
    # If you chain organization reports and url reports, same memory issue happens.
    # and because you don't know the order of things happening, usually fifo. So it is guaranteed that a few
    # reports will be rated before url ratings happen. But because the queue is fifo you can add dummy tasks
    # to create a buffer between tasks instead of chaining.
    return group(tasks)


@app.task(queue="reporting")
def calculate_vulnerability_statistics_specific(map_configuration, days_back):
    metadata = get_backend_scanmetadata()
    scan_types = {"total"}
    country = map_configuration["country"]
    organization_type_id = map_configuration["organization_type"]

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
    when = datetime.now(timezone.utc) - timedelta(days=days_back)
    log.info("Days back:%s Date: %s", days_back, when)

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
    # sql = """SELECT reporting_urlreport.id as id, reporting_urlreport.id as my_id,
    #                 reporting_urlreport.total_endpoints,
    #                 reporting_urlreport2.calculation as calculation, url.id as url_id2
    #        FROM reporting_urlreport
    #        INNER JOIN
    #        (SELECT MAX(id) as id2 FROM reporting_urlreport or2
    #        WHERE at_when <= '%(when)s' GROUP BY url_id) as x
    #        ON x.id2 = reporting_urlreport.id
    #        INNER JOIN url ON reporting_urlreport.url_id = url.id
    #        INNER JOIN url_organization on url.id = url_organization.url_id
    #        INNER JOIN organization ON url_organization.organization_id = organization.id
    #        INNER JOIN reporting_urlreport as reporting_urlreport2
    #             ON reporting_urlreport2.id = reporting_urlreport.id
    #         WHERE organization.type_id = '%(OrganizationTypeId)s'
    #         AND organization.country = '%(country)s'
    #         AND reporting_urlreport.total_endpoints > 0
    #         ORDER BY reporting_urlreport.url_id
    #     """ % {
    #     "when": when,
    #     "OrganizationTypeId": organization_type_id,
    #     "country": country,
    # }

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
              INNER JOIN organization_layers as layers4 ON (layers4.organization_id = stacked_organization.id)
              WHERE (
                stacked_organization.created_on <= '%(when)s'
                AND stacked_organization.is_dead = 0
                AND stacked_organization.country='%(country)s'
                AND layers4.organizationtype_id = %(OrganizationTypeId)s
                )
              OR (
              '%(when)s' BETWEEN stacked_organization.created_on AND stacked_organization.is_dead_since
                AND stacked_organization.is_dead = 1
                AND stacked_organization.country='%(country)s'
                AND layers4.organizationtype_id = %(OrganizationTypeId)s
              )) as organization_stack
              ON organization_stack.stacked_organization_id = map_organizationreport.organization_id


            INNER JOIN
              organization on organization.id = stacked_organization_id
            INNER JOIN organization_layers ON (organization_layers.organization_id = organization.id)

            INNER JOIN
              organizations_organizationtype on
              organizations_organizationtype.id = organization_layers.organizationtype_id
            INNER JOIN

              (SELECT MAX(stacked_coordinate.id) as stacked_coordinate_id, area, geoJsonType,
                 stacked_coordinate.organization_id
              FROM coordinate stacked_coordinate
              INNER JOIN organization filter_organization
                ON (stacked_coordinate.organization_id = filter_organization.id)
              INNER JOIN organization_layers as layers3 ON (layers3.organization_id = filter_organization.id)
              WHERE (
                stacked_coordinate.created_on <= '%(when)s'
                AND stacked_coordinate.is_dead = 0
                AND filter_organization.country='%(country)s'
                AND layers3.organizationtype_id=%(OrganizationTypeId)s
                )
              OR
                ('%(when)s' BETWEEN stacked_coordinate.created_on AND stacked_coordinate.is_dead_since
                AND stacked_coordinate.is_dead = 1
                AND filter_organization.country='%(country)s'
                AND layers3.organizationtype_id=%(OrganizationTypeId)s
                ) GROUP BY calculated_area_hash, stacked_coordinate.organization_id
              ) as coordinate_stack
              ON coordinate_stack.organization_id = map_organizationreport.organization_id


            INNER JOIN


              (SELECT MAX(map_organizationreport.id) as stacked_organizationrating_id
              FROM map_organizationreport
              INNER JOIN organization filter_organization2
                ON (filter_organization2.id = map_organizationreport.organization_id)
              INNER JOIN organization_layers as layers2 ON (layers2.organization_id = filter_organization2.id)
              WHERE at_when <= '%(when)s'
              AND filter_organization2.country='%(country)s'
              AND layers2.organizationtype_id=%(OrganizationTypeId)s
              GROUP BY map_organizationreport.organization_id
              ) as stacked_organizationrating
              ON stacked_organizationrating.stacked_organizationrating_id = map_organizationreport.id

            WHERE organization_layers.organizationtype_id = '%(OrganizationTypeId)s'
             AND organization.country= '%(country)s'
            GROUP BY coordinate_stack.area, organization.name
            ORDER BY map_organizationreport.at_when ASC
            """ % {
        "when": when,
        "OrganizationTypeId": organization_type_id,
        "country": country,
    }

    organizationratings = OrganizationReport.objects.raw(sql)

    needed_reports = [str(organizationrating.pk) for organizationrating in organizationratings]

    reports = get_reports_by_ids(needed_reports)

    direct_reports = [reports[report] for report in reports]
    number_of_endpoints = 0
    number_of_urls = 0
    # log.debug(sql)

    # some urls are in multiple organizaitons, make sure that it's only shown once.
    processed_urls = []

    for direct_report in direct_reports:
        # log.debug("Processing rating of %s " %
        #     organizationrating.calculation["organization"].get("name", "UNKOWN"))

        # perhaps a crashed or empty report.
        if not direct_report:
            continue

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

                # if explained and explanation valid right now, then mark it down as OK so the
                # statistics matches the report. -> or is this always done?
                measurement[rating["type"]]["applicable_urls"] += 1

                if rating["is_explained"] and rating["comply_or_explain_valid_at_time_of_report"]:
                    # if any other score is actually of value, then place it into ok.
                    # in all cases this should just result into += 1
                    # don't store explained stuff as a separate field yet
                    measurement[rating["type"]]["ok_urls"] += rating["high"] + rating["medium"] + rating["low"]
                    measurement["total"]["ok_urls"] += rating["high"] + rating["medium"] + rating["low"]
                else:
                    measurement[rating["type"]]["high"] += rating["high"]
                    measurement[rating["type"]]["medium"] += rating["medium"]
                    measurement[rating["type"]]["low"] += rating["low"]
                    measurement[rating["type"]]["ok_urls"] += rating["ok"]

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

                    measurement[rating["type"]]["applicable_endpoints"] += 1

                    if rating["is_explained"] and rating["comply_or_explain_valid_at_time_of_report"]:
                        measurement["total"]["ok_endpoints"] += rating["high"] + rating["medium"] + rating["low"]
                        measurement[rating["type"]]["ok_endpoints"] += rating["high"] + rating["medium"] + rating["low"]
                    else:
                        measurement[rating["type"]]["high"] += rating["high"]
                        measurement[rating["type"]]["medium"] += rating["medium"]
                        measurement[rating["type"]]["low"] += rating["low"]
                        measurement[rating["type"]]["ok_endpoints"] += rating["ok"]

                        measurement["total"]["high"] += rating["high"]
                        measurement["total"]["medium"] += rating["medium"]
                        measurement["total"]["low"] += rating["low"]
                        measurement["total"]["ok_endpoints"] += rating["ok"]

    # store these results per scan type, and only retrieve this per scan type...
    for scan_type in scan_types:
        # log.debug(scan_type)
        if scan_type in measurement:
            vstat = VulnerabilityStatistic()
            vstat.at_when = when
            vstat.organization_type = OrganizationType(pk=organization_type_id)
            vstat.country = country
            vstat.scan_type = scan_type
            vstat.high = measurement[scan_type]["high"]
            vstat.medium = measurement[scan_type]["medium"]
            vstat.low = measurement[scan_type]["low"]
            vstat.ok_urls = measurement[scan_type]["ok_urls"]
            vstat.ok_endpoints = measurement[scan_type]["ok_endpoints"]

            if scan_type in metadata["published_scan_types"]:
                vstat.urls = measurement[scan_type]["applicable_urls"]
                vstat.endpoints = measurement[scan_type]["applicable_endpoints"]
            else:
                # total
                vstat.urls = number_of_urls
                vstat.endpoints = number_of_endpoints

            if scan_type in metadata["endpoint_scan_types"]:
                vstat.ok = measurement[scan_type]["ok_endpoints"]  # pylint: disable=invalid-name
            elif scan_type in metadata["url_scan_types"]:
                vstat.ok = measurement[scan_type]["ok_urls"]
            else:
                # total: everything together.
                vstat.ok = measurement[scan_type]["ok_urls"] + measurement[scan_type]["ok_endpoints"]

            vstat.save()


def sync_model_field_to_disk(model, json_field, file_field):
    # moves the data from .dataset (a json dumps) to a zipped storage in .dataset_file

    # dataset is deferred as mysql will not load the full table into django memory etc...
    # removed .defer(json_field) - otherwise it wont pass tests, so lets just try and see if this works...
    for mdc in model.objects.all():
        # you'll get a warning for this record being accessed as N+1, as we just deferred this field.
        if not getattr(mdc, json_field):
            # already migrated
            continue

        data = getattr(mdc, json_field)
        setattr(mdc, json_field, None)
        setattr(mdc, file_field, transparent_json_to_zip_storage(data))
        mdc.save()


def calculate_map_data(days: int = 366, countries: List = None, organization_types: List = None):
    metadata = get_backend_scanmetadata()

    log.info("calculate_map_data")

    map_configurations = filter_map_configs(countries=countries, organization_types=organization_types)

    # the "all" filter will retrieve all layers at once
    scan_types = ["all"] + metadata["published_scan_types"]

    tasks = []

    for map_configuration in map_configurations:
        for days_back in list(reversed(range(days))):
            when = datetime.now(timezone.utc) - timedelta(days=days_back)
            tasks.extend(calculate_map_data_specific.si(map_configuration, when, scan_type) for scan_type in scan_types)
    return tasks


@app.task(queue="reporting")
def calculate_map_data_specific(map_configuration, when, scan_type):
    ot = map_configuration["organization_type"]
    otn = map_configuration["organization_type__name"]
    country = map_configuration["country"]

    # You can expect something to change each day. Therefore just store the map data each day.
    try:
        MapDataCache.objects.all().filter(
            at_when=when,
            country=country,
            organization_type=OrganizationType(pk=ot),
            filters=[scan_type],
        ).delete()
    except Exception:
        log.exception("failed to delete old mapdatacache")

    log.info("Country: %s, Organization_type: %s, date: %s, filter: %s", country, otn, when, scan_type)

    data = get_map_data(country, otn, 0, scan_type, when)

    try:
        cached = MapDataCache()
        cached.organization_type = OrganizationType(pk=ot)
        cached.country = country
        cached.filters = [scan_type]
        cached.at_when = when
        cached.dataset = None
        cached.dataset_file = transparent_json_to_zip_storage(data)
        cached.save()
    except OperationalError as my_exception:
        # The public user does not have permission to run insert statements....
        log.exception(my_exception)


def calculate_high_level_stats(days: int = 1, countries: List = None, organization_types: List = None) -> List[Task]:
    log.info("Creating high_level_stats")

    map_configurations = filter_map_configs(countries=countries, organization_types=organization_types)

    tasks = []
    for map_configuration in map_configurations:
        tasks.extend(
            calculate_high_level_stats_specific.si(map_configuration, days_back)
            for days_back in list(reversed(range(days)))
        )
    return tasks


def calculate_vulnerability_statistics(days: int = 366, countries: List = None, organization_types: List = None):
    log.info("Calculation vulnerability graphs")

    map_configurations = filter_map_configs(countries=countries, organization_types=organization_types)

    tasks = []
    for map_configuration in map_configurations:
        tasks.extend(
            calculate_vulnerability_statistics_specific.si(map_configuration, days_back)
            for days_back in list(reversed(range(days)))
        )
    return tasks


@app.task(queue="reporting")
def calculate_high_level_stats_specific(map_configuration, days_back):
    log.debug(
        "For country: %s type: %s days back: %s",
        map_configuration["country"],
        map_configuration["organization_type__name"],
        days_back,
    )

    when = datetime.now(timezone.utc) - timedelta(days=days_back)

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
            INNER JOIN organization_layers as layers ON (layers.organization_id = filter_organization.id)
            WHERE
                at_when <= '%(when)s'
                AND filter_organization.country='%(country)s'
                AND layers.organizationtype_id=%(OrganizationTypeId)s
           GROUP BY or2.organization_id
        ) as stacked_organizationreport
        ON stacked_organizationreport.id2 = map_organizationreport.id
        INNER JOIN organization ON map_organizationreport.organization_id = organization.id
        INNER JOIN organization_layers as layers1 ON (layers1.organization_id = organization.id)
        WHERE
            /* Only include organizations that are alive now... */
            (('%(when)s' BETWEEN organization.created_on AND organization.is_dead_since
            AND organization.is_dead = 1
            ) OR (
            organization.created_on <= '%(when)s'
            AND organization.is_dead = 0
            ))
            AND layers1.organizationtype_id = '%(OrganizationTypeId)s'
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

    needed_reports = [str(organizationrating.id) for organizationrating in ratings]
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
        calculation = reports[str(rating.id)]
        measurement["total_urls"] += len(calculation["organization"]["urls"])

        measurement["good_urls"] += sum(
            lx["high"] == 0 and lx["medium"] == 0 for lx in calculation["organization"]["urls"]
        )

        measurement["medium_urls"] += sum(
            lx["high"] == 0 and lx["medium"] > 0 for lx in calculation["organization"]["urls"]
        )

        measurement["high_urls"] += sum(lx["high"] > 0 for lx in calculation["organization"]["urls"])

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
            for rat in url["ratings"]:
                # stats over all different ratings
                if rat["type"] not in measurement["explained"]:
                    measurement["explained"][rat["type"]] = {"total": 0}
                if not rat["explanation"].startswith("Repeated finding."):
                    if rat["explanation"] not in measurement["explained"][rat["type"]]:
                        measurement["explained"][rat["type"]][rat["explanation"]] = 0

                    measurement["explained"][rat["type"]][rat["explanation"]] += 1
                    measurement["explained"][rat["type"]]["total"] += 1

            for endpoint in url["endpoints"]:
                # Only add the endpoint once for a series of ratings. And only if the
                # ratings is not a repeated finding.
                added_endpoint = False

                for rat in endpoint["ratings"]:
                    # stats over all different ratings
                    if rat["type"] not in measurement["explained"]:
                        measurement["explained"][rat["type"]] = {"total": 0}
                    if not rat["explanation"].startswith("Repeated finding."):
                        if rat["explanation"] not in measurement["explained"][rat["type"]]:
                            measurement["explained"][rat["type"]][rat["explanation"]] = 0

                        measurement["explained"][rat["type"]][rat["explanation"]] += 1
                        measurement["explained"][rat["type"]]["total"] += 1

                        # stats over all endpoints
                        # duplicates skew these stats.
                        # it is possible to have multiple endpoints of the same type
                        # while you can have multiple ipv4 and ipv6, you can only reach one
                        # therefore reduce this to have only one v4 and v6
                        if not added_endpoint:
                            added_endpoint = True
                            endpointtype = (
                                f"{endpoint['protocol']}/{endpoint['port']} "
                                f"({('IPv4' if endpoint['ip_version'] == 4 else 'IPv6')})"
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
        measurement["high percentage"] = round((measurement["high"] / measurement["included_organizations"]) * 100)
        measurement["medium percentage"] = round((measurement["medium"] / measurement["included_organizations"]) * 100)
        measurement["good percentage"] = round((measurement["good"] / measurement["included_organizations"]) * 100)
    else:
        measurement["high percentage"] = 0
        measurement["medium percentage"] = 0
        measurement["good percentage"] = 0

    if measurement["total_urls"]:
        measurement["high url percentage"] = round((measurement["high_urls"] / measurement["total_urls"]) * 100)
        measurement["medium url percentage"] = round((measurement["medium_urls"] / measurement["total_urls"]) * 100)
        measurement["good url percentage"] = round((measurement["good_urls"] / measurement["total_urls"]) * 100)
    else:
        measurement["high url percentage"] = 0
        measurement["medium url percentage"] = 0
        measurement["good url percentage"] = 0

    stat = HighLevelStatistic()
    stat.country = map_configuration["country"]
    stat.organization_type = OrganizationType.objects.get(name=map_configuration["organization_type__name"])
    stat.at_when = when
    stat.report = measurement
    stat.save()


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
        when = datetime.now(timezone.utc)

    log.info("Creating report for %s on %s", organization, when)

    # if there already is an organization rating on this moment, skip it. You should have deleted it first.
    # this is probably a lot quicker than calculating the score and then deepdiffing it.
    # using this check we can also ditch deepdiff, because ratings on the same day are always the same.
    # todo: we should be able to continue on a certain day.
    if OrganizationReport.objects.all().filter(organization=organization, at_when=when).exists():
        log.info("Rating already exists for %s on %s. Not overwriting.", organization, when)

    # Done: closing off urls, after no relevant endpoints, but still resolvable. Done.
    # if so, we don't need to check for existing endpoints anymore at a certain time...
    # It seems we don't need the url object, only a flat list of pk's for urlratigns.
    # urls = relevant_urls_at_timepoint(organizations=[organization], when=when)
    urls = relevant_urls_at_timepoint_organization(organization=organization, when=when)

    # Here used to be a lost of nested queries: getting the "last" one per url. This has been replaced with a
    # custom query that is many many times faster.
    all_url_ratings = get_latest_urlratings_fast(urls, when)
    # when is relevant because you want to see if the explanation has not expired.
    scores = aggegrate_url_rating_scores(all_url_ratings, at_when=when)

    # disabled deepdiff, see below, it doesn't save anything in usual modus operandi
    # Still do deepdiff to prevent double reports.
    # try:
    #     last = (
    #         OrganizationReport.objects.filter(organization=organization, at_when__lte=when)
    #         .defer("calculation")
    #         .latest("at_when")
    #     )
    # except OrganizationReport.DoesNotExist:
    #     log.debug("Could not find the last organization rating, creating a dummy one.")
    #     last = OrganizationReport()  # create an empty one

    scores["name"] = organization.name
    calculation = {"organization": scores}

    # since metrics change basically every day, don't deepdiff or try to optimize and just save the report
    # every day. Dates of 'last scan' will be different anyway as at least one metric will be performed.
    # this only would save data if there was no scan performed!
    save_organization_report_on_moment(organization, when, scores, calculation)

    # therefore this has been commented out:
    # this is 10% faster without deepdiff, the major pain is elsewhere.
    # last_report_data = retrieve_report(last.id, "OrganizationReport")
    # if DeepDiff(last_report_data, calculation, ignore_order=True, report_repetition=True):
    #     save_organization_report_on_moment(organization, when, scores, calculation)

    # else:
    #     # This happens because some urls are dead etc: our filtering already removes this from the relevant info
    #     # at this point in time. But since it's still a significant moment, it will just show that nothing changed.
    #     log.warning("The calculation for %s on %s is the same as the previous one. Not saving.", organization, when)


def save_organization_report_on_moment(organization, when, scores, calculation):
    log.info("The calculation for %s on %s should have changed, so we're saving this rating.", organization, when)

    # remove urls and name from scores object, so it can be used as initialization parameters (saves lines)
    # this is by reference, meaning that the calculation will be affected if we don't work on a clone.
    init_scores = deepcopy(scores)
    del init_scores["name"]
    del init_scores["urls"]

    organizationrating = OrganizationReport(**init_scores)
    organizationrating.organization = organization
    organizationrating.at_when = when
    organizationrating.calculation = None
    organizationrating.save()

    store_report(organizationrating.pk, "OrganizationReport", calculation)

    log.info("Saved report for %s on %s.", organization, when)


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

        log.info("Giving organization a default rating: %s", organization)

        when = organization.created_on or START_DATE

        report = OrganizationReport()
        report.at_when = when
        report.organization = organization
        report.calculation = None
        report.save()

        default_calculation = {
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
                "url_ok": 0,
                "endpoint_issues_high": 0,
                "endpoint_issues_medium": 0,
                "endpoint_issues_low": 0,
                "endpoint_ok": 0,
                "urls": [],
                "total_issues": 0,
            }
        }
        store_report(report.id, "OrganizationReport", default_calculation)


@app.task(queue="reporting")
def create_organization_reports_now(organizations: List[int]):
    for organization_id in organizations:
        organization = Organization.objects.all().filter(id=organization_id).first()
        if not organization:
            continue

        now = datetime.now(timezone.utc)
        create_organization_report_on_moment(organization, now)


@app.task(queue="reporting")
def recreate_organization_reports(organizations: List[int]):
    """Remove organization rating and rebuild a new."""

    # todo: only for allowed organizations...
    metadata = get_backend_scanmetadata()

    for organization_id in organizations:
        organization = Organization.objects.all().filter(id=organization_id).first()
        if not organization:
            continue

        log.info("Adding rating for organization %s", organization)

        # Given this is a rebuild, delete all previous reports;
        OrganizationReport.objects.all().filter(organization=organization).delete()

        # and then rebuild the ratings per moment, which is a maximum of one per day.
        urls = Url.objects.filter(organization__in=organizations)
        moments, _ = significant_moments(urls=urls, reported_scan_types=metadata["published_scan_types"]())

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
    some_day_a_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
    some_day_a_two_years_ago = datetime.now(timezone.utc) - timedelta(days=730)

    to_reduce_to_days = [moment for moment in moments if moment > some_day_a_year_ago]
    # log.debug(f"To days: {to_reduce_to_days}")
    results += reduce_to_days(to_reduce_to_days)

    to_reduce_to_weeks = [
        moment
        for moment in moments
        if
        # not simplyfying the chain expression, as i can't understand what is being said clear enough
        some_day_a_two_years_ago < moment <= some_day_a_year_ago
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
        (_, amount_of_days_in_month) = calendar.monthrange(moment.year, moment.month)
        if datetime(moment.year, moment.month, amount_of_days_in_month, tzinfo=timezone.utc) not in reduced_datetimes:
            reduced_datetimes.append(datetime(moment.year, moment.month, amount_of_days_in_month, tzinfo=timezone.utc))

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
    reduced_datetimes: List[date] = list({moment.date() for moment in moments})

    return [
        datetime(year=moment.year, month=moment.month, day=moment.day, tzinfo=timezone.utc)
        for moment in reduced_datetimes
    ]


def set_dates_to_last_possible_moment(moments: List[datetime]) -> List[datetime]:
    return [
        datetime(moment.year, moment.month, moment.day, 23, 59, 59, 999999, tzinfo=timezone.utc) for moment in moments
    ]


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

        tasks.append(group(recreate_url_reports([url.id])) | create_organization_reports_now.si(organizations))

        # Calculating statistics is _extremely slow_ so we're not doing that in this method to keep the pace.
        # Otherwise you'd have a 1000 statistic rebuilds pending, all doing a marginal job.
        # calculate_vulnerability_statistics.si(1) | calculate_map_data.si(1)

    return group(tasks)

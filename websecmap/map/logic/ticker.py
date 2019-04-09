from datetime import timedelta

from constance import config

from websecmap.map.logic.map_defaults import get_country, get_organization_type, get_when
from websecmap.map.models import OrganizationReport


def get_ticker_data(country: str = "NL", organization_type: str = "municipality",
                    weeks_back: int = 0, weeks_duration: int = 0):

    weeks_back = int(weeks_back)
    weeks_duration = int(weeks_duration)

    # Gives ticker data of organizations, like in news scrolling:
    # On organization level, could be on URL level in the future (selecing more cool urls?)
    # Organizations are far more meaningful.
    # Amsterdam 42 +1, 32 +2, 12 -, Zutphen 12 -3, 32 -1, 3 +3, etc.

    if not weeks_duration:
        weeks_duration = 10

    when = get_when(weeks_back)

    # looks a lot like graphs, but then just subtract/add some values and done (?)

    # compare the first urlrating to the last urlrating
    # but do not include urls that don't exist.

    # the query is INSTANT!
    sql = """SELECT map_organizationreport.id as id, name, high, medium, low FROM
               map_organizationreport
           INNER JOIN
           (SELECT MAX(id) as id2 FROM map_organizationreport or2
           WHERE `when` <= '%(when)s' GROUP BY organization_id) as x
           ON x.id2 = map_organizationreport.id
           INNER JOIN organization ON map_organizationreport.organization_id = organization.id
            WHERE organization.type_id = '%(OrganizationTypeId)s'
            AND organization.country = '%(country)s'
        """ % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
               "country": get_country(country)}

    newest_urlratings = list(OrganizationReport.objects.raw(sql))

    # this of course doesn't work with the first day, as then we didn't measure
    # everything (and the ratings for several issues are 0...
    sql = """SELECT map_organizationreport.id as id, name, high, medium, low FROM
               map_organizationreport
           INNER JOIN
           (SELECT MAX(id) as id2 FROM map_organizationreport or2
           WHERE `when` <= '%(when)s' GROUP BY organization_id) as x
           ON x.id2 = map_organizationreport.id
           INNER JOIN organization ON map_organizationreport.organization_id = organization.id
            WHERE organization.type_id = '%(OrganizationTypeId)s'
            AND organization.country = '%(country)s'
        """ % {"when": when - timedelta(days=(weeks_duration * 7)),
               "OrganizationTypeId": get_organization_type(organization_type),
               "country": get_country(country)}

    oldest_urlratings = list(OrganizationReport.objects.raw(sql))

    # create a dict, where the keys are pointing to the ratings. This makes it easy to match the
    # correct ones. And handle missing oldest ratings for example.
    oldest_urlratings_dict = {}
    for oldest_urlrating in oldest_urlratings:
        oldest_urlratings_dict[oldest_urlrating.name] = oldest_urlrating

    # insuccesful rebuild? Or not enough organizations?
    if not newest_urlratings:
        return {'changes': {}, 'slogan': config.TICKER_SLOGAN}

    changes = []
    for newest_urlrating in newest_urlratings:

        try:
            matching_oldest = oldest_urlratings_dict[newest_urlrating.name]
        except KeyError:
            matching_oldest = None

        if not matching_oldest:
            high_then = medium_then = low_then = "-"
            high_changes = newest_urlrating.high
            medium_changes = newest_urlrating.medium
            low_changes = newest_urlrating.low

        else:
            high_then = matching_oldest.high
            medium_then = matching_oldest.medium
            low_then = matching_oldest.low
            high_changes = newest_urlrating.high - matching_oldest.high
            medium_changes = newest_urlrating.medium - matching_oldest.medium
            low_changes = newest_urlrating.low - matching_oldest.low

        change = {
            'organization': newest_urlrating.name,
            'high_now': newest_urlrating.high,
            'medium_now': newest_urlrating.medium,
            'low_now': newest_urlrating.low,
            'high_then': high_then,
            'medium_then': medium_then,
            'low_then': low_then,
            'high_changes': high_changes,
            'medium_changes': medium_changes,
            'low_changes': int(low_changes),
        }

        changes.append(change)

    data = {'changes': changes, 'slogan': config.TICKER_SLOGAN}

    return data

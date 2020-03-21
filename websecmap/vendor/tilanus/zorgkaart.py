#!/usr/bin/python3
# Note: run make fix and make check before committing code.

"""
Scrapes organisations from Zorgkaart Nederland API
provides the task: vendor.tilanus.zorgkaart.scrape
uses websecmap config as parameters

organisations()
    Returns list of organsations in data structure
    as returned by zorgkaart Nederland. Applies
    filters as set in config.
    DANGER LOTS OF OUTPUT WHEN NOT FILTERED

organisation_types()
    Returns a list of organisation types as currently
    present in the zorgkaart Nederland database.

translate(organisation_list)
    Translates the Zorgkaart Nederland organisations list
    to a list that can be imprted into WebSecMap.

scrape()
    Retrieves list of organisations (applying filter in
    WebSecMap config) and translates and inserts/updates
    them into the database of WebSecMap.

create_task()
    Inserts a periodic task for running the scraper weekly
    into the WebSecMap configuration.
"""

import json
import logging
import sys

import urllib3
# websecmap modules
from constance import config
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from websecmap.api.logic import organization_and_url_import

_all_ = organization_and_url_import

# Periodic task name
TaskName = 'zorgkaart import (hidden)'

# right now we there is a page limit of 1000 and max 123000 items
# so the the default limit of 1000 is OK but not future proof
# raise it for all security
sys.setrecursionlimit(10000)

# logging
log = logging.getLogger(__package__)

# debug error info


def create_task():
    """Adds scraping task to celery jobs"""
    if not PeriodicTask.objects.get(name=TaskName):
        p = PeriodicTask(**{"name": TaskName, "task": "vendor.tilanus.zorgkaart.scrape",
                            "crontab": CrontabSchedule.objects.get(id=7)})
        p.save()
        log.info(f"Created Periodic Task for zorgkaart scraper with name: {TaskName}")


def do_request(url, params={}, previous_items=[]):
    """Internal function, performs API requests and merges paginated data"""
    # default to max limit of API
    if not 'limit' in params.keys():
        params['limit'] = 10000
    # set page
    if not 'page' in params.keys():
        params['page'] = 1
    log.debug(f"Zorgkaart scraper request with parameters: {params}")
    # setup for API call use Debian ca-certificats
    http = urllib3.PoolManager(
        cert_reqs='CERT_REQUIRED',
        ca_certs='/etc/ssl/certs/ca-certificates.crt')
    headers = urllib3.util.make_headers(basic_auth=config.ZORGKAART_USERNAME+":"+config.ZORGKAART_PASSWORD)
    # do request
    r = http.request('GET', url, headers=headers, fields=params)
    if not r.status == 200:
        raise Exception(f"Zorgkaart scraper got an non 200 status from zorgkaart: {r.status}")
    # load in python stuctures
    result = json.loads(r.data.decode('utf8'))
    # merge with results from reursions above
    items = previous_items+result["items"]
    # do we have everything
    if result["count"] > result["page"]*result["limit"]:
        # recursion because recursive programming is utterly uncomprehensible but fun
        params['page'] += 1
        log.debug(f"Zorgkaat scraper requesting nest page: {params['page']}")
        items = do_request(url, params, items)
    else:
        if not result["count"] == len(items):
            log.error(
                f"Zogkaart scraper: the amount of records reported by Zorgkaart ({result['count']}) is not equal to the amount of records recieved ({len(itmes)})")
    return items


def organisations():
    """
    Get a list of organisations as present in Zorgkaart

    returns:
        a list of dicts, datastructure as provided by Zorgkaart
    """
    params = json.loads(config.ZORGKAART_FILTER)
    if not type(params) == dict:
        log.error(f"Zorgkaat scrape: invalid filter ({params}), ignoring")
        params = {}
    log.debug(f"Zorgkaart scraper requesting organisations using filter: {params}")
    items = do_request(config.ZORGKAART_ENDPOINT, params)
    return items


def organisation_types():
    """
    get a list of organisation types present in Zorgkaart

    returns:
        a list of dicts with keys: 'id' (str) and 'name' (str)
    """
    url = "https://api.zorgkaartnederland.nl/api/v1/companies/types"
    items = do_request(url)
    return items


def translate(orglist):
    """
    translates a list of organisations as provided by Zorgkaart into a list of
    organisations that can be imported into WebSecMap.

    arguments:
        orglist - a list Zorgkaart-type list of organisations

    Returns:
        a list of dicts containing data that can be imported into WebSecMap.
    """
    outlist = []
    for org in orglist:
        outlist.append({
            'name': org['name'] + ' (' + org['type'] + ')',
            'layer': 'Zorg',
            'country': 'NL',
            'coordinate_type': 'Point',
            'coordinate_area': [org['location']['longitude'], org['location']['latitude']],
            'address': org['addresses'][0]['address'] + ', ' + org['addresses'][0]['zipcode'] + ' ' + org['addresses'][0]['city'] + ', ' + org['addresses'][0]['country'],
            'surrogate_id': org['name']+'_'+org['type']+'_'+org['id'],
            'urls': org['websites']
        })
    return outlist


def scrape():
    """
    Retrieves list of organisations (applying the filter in
    WebSecMap config) and translates and inserts/updates
    them into the database of WebSecMap.
    """
    orglist = organisations()
    wsmlist = translate(orglist)
    organization_and_url_import(wsmlist)
    log.info(f"Zorgkaart scrape updated organisations. Current organisation count: {len(orglist)}")
    return

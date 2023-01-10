import itertools
import logging
import random
import re
import string
import tempfile
from datetime import datetime
from time import sleep
from typing import Any, Dict, List

import pytz
import requests
from celery import Task, group
from django.db import connection
from django.db.models import Q
from dnsrecon.__main__ import brute_domain, ds_zone_walk
from dnsrecon.lib.dnshelper import DnsHelper
from requests import RequestException

from websecmap.celery import EXPIRES_IN_ONE_DAY, app
from websecmap.map.logic.map_defaults import get_country
from websecmap.organizations.models import Organization, Url
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.scanner.__init__ import q_configurations_to_scan, unique_and_random, url_filters
from websecmap.scanners.scanner.http import get_ips

# Include DNSRecon code from an external dependency. This is cloned recursively and placed outside the django app.
from websecmap.scanners.scanner.utils import get_random_nameserver
from websecmap.scanners.timeout import timeout

log = logging.getLogger(__package__)


def url_by_filters(organizations_filter: dict = None, urls_filter: dict = None) -> List:
    organizations_filter, urls_filter = init_dict(organizations_filter, urls_filter)

    # only include what is allowed to be scanned, and reduce the amount of retrieved fields to a minimum.
    urls = Url.objects.all().filter(q_configurations_to_scan(level="url"), **urls_filter).only("id", "url")

    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter).only("id")
        urls = urls.filter(
            Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
            organization__in=organizations,
            do_not_find_subdomains=False,
        )
    else:
        urls = urls.filter(Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""), do_not_find_subdomains=False)

    urls = unique_and_random(urls)

    return urls


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def plan_discover(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs):
    organizations_filter, urls_filter = init_dict(organizations_filter, urls_filter)
    urls = url_by_filters(organizations_filter=organizations_filter, urls_filter=urls_filter)
    plannedscan.request(activity="discover", scanner="subdomains", urls=urls)


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def compose_planned_discover_task(**kwargs):
    urls = plannedscan.pickup(activity="discover", scanner="subdomains", amount=kwargs.get("amount", 25))
    return compose_discover_task(urls)


def compose_manual_discover_task(organizations_filter: dict = None, urls_filter: dict = None, **kwargs):
    organizations_filter, urls_filter = init_dict(organizations_filter, urls_filter)
    urls = url_by_filters(organizations_filter=organizations_filter, urls_filter=urls_filter)
    log.info("Discovering subdomains on %s urls.", len(urls))
    return compose_discover_task(urls)


def compose_discover_task(urls: List[Url]) -> Task:
    return group(
        certificate_transparency_scan.si(url.url)
        | store_certificate_transparency_results.s(url.id)
        | nsec_scan.si(url.url)
        | dnsrecon_parse_report_contents.s(url.as_dict())
        | plannedscan.finish.si("discover", "subdomains", url.pk)
        for url in urls
    )


def filter_verify(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)

    default_filter = {"not_resolvable": False}
    # The urls filter will overwrite the default filter in this case. Used in verify unresolvable
    urls_filter = {**default_filter, **urls_filter}

    urls = Url.objects.all().filter(q_configurations_to_scan(level="url"))
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter).only("id", "url", "not_resolvable")

    return unique_and_random(urls)


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def plan_verify(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)

    urls = filter_verify(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity="verify", scanner="subdomains", urls=urls)


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def compose_planned_verify_task(**kwargs):
    urls = plannedscan.pickup(activity="verify", scanner="subdomains", amount=kwargs.get("amount", 25))
    return compose_verify_task(urls)


# it will not revive anything(!) Should that be a revive task?
def compose_manual_verify_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> Task:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)

    # instead of only checking by domain, just accept the filters as they are handled in any other scenario...
    urls = filter_verify(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    log.info("Will verify subdomain resolvability via DNS on %s urls", len(urls))

    return compose_verify_task(urls)


def compose_verify_task(urls):
    return group(
        url_resolves.si(url.url) | handle_resolves.s(url.pk) | plannedscan.finish.si("verify", "subdomains", url.pk)
        for url in urls
    )


def filter_discover(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)

    default_filter = {"not_resolvable": False}
    # The urls filter will overwrite the default filter in this case. Used in verify unresolvable
    urls_filter = {**default_filter, **urls_filter}

    urls = Url.objects.all().filter(q_configurations_to_scan(level="url"))
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter).only("id", "url", "not_resolvable")

    urls = list(set(urls))
    random.shuffle(urls)


# this is so fast, the overhead on running this elsewhere is insane... requires both ipv4 and 6 capabilities
@app.task(queue="internet")
def url_resolves(url: str):
    ipv4, ipv6 = get_ips(url)
    return bool(ipv4 or ipv6)


@app.task(queue="storage")
def handle_resolves(resolves: bool, url_id: int) -> None:

    url = Url.objects.all().filter(pk=url_id).first()
    if not url:
        return

    if not resolves and url.not_resolvable is False:
        url.not_resolvable = True
        url.not_resolvable_reason = "DNS did not resolve (DNS verify task)"
        url.not_resolvable_since = datetime.now(pytz.utc)
        url.save()

    if resolves and url.not_resolvable is True:
        url.not_resolvable = False
        url.not_resolvable_reason = "DNS found the url to resolve"
        url.not_resolvable_since = None
        url.save()

    return


def toplevel_urls(organizations):
    return Url.objects.all().filter(organization__in=organizations, computed_subdomain="")


# This helps to determine at database level if the DNS uses wildcards, so it can be dealt
# with in another way.
def toplevel_urls_without_wildcards(organizations: List):
    return Url.objects.all().filter(organization__in=organizations, computed_subdomain="", uses_dns_wildcard=False)


def remove_and_save_wildcards(urls: List[Dict[str, Any]]):
    without_wildcards, _ = has_wildcards(urls)
    return without_wildcards


def has_wildcards(urls: List[Dict[str, Any]]):
    """Run this when adding a new url.

    So you can be sure that there are no wildcards if you don't want them.

    Of course the DNS can change every day, so you never know for sure.
    """

    urls_with_wildcards = []
    urls_without_wildcards = []

    for url in urls:

        db_url = Url.objects.all().filter(pk=url["id"]).first()
        if not db_url:
            continue

        if url_discover_wildcard(url["url"]):
            log.info("Domain %s uses wildcards, DNS brute force not possible", url["url"])
            db_url.uses_dns_wildcard = True
            urls_with_wildcards.append(url)
        else:
            db_url.uses_dns_wildcard = False
            urls_without_wildcards.append(url)
        db_url.save()

    log.debug(
        "Of the %s urls, %s had a wildcard and %s did not.",
        len(urls),
        len(urls_with_wildcards),
        len(urls_without_wildcards),
    )

    return urls_without_wildcards, urls_with_wildcards


def url_discover_wildcard(url: Url):
    return discover_wildcard(url.url)


@app.task(queue="internet")
def discover_wildcard(url: str):
    """
    We need to perform a check ourselves, since we cannot get from the DNSRecon report if the url
    uses wildcards. We store this ourselves so we can better filter domains.

    In some cases DNSrecon makes a wrong assumption about wildcard usage. This is hopefully a bit better.
    """
    log.debug("Checking for DNS wildcards on domain: %s", url)

    resolver = DnsHelper(url, [get_random_nameserver()], 3)

    # Do this test twice, there are dns servers that say NO the first time, but say yes the second (i mean wtf)
    ips_1 = resolver.get_a(f"{''.join(random.choice(string.ascii_lowercase) for _ in range(16))}.{url}")
    ips_2 = resolver.get_a(f"{''.join(random.choice(string.ascii_lowercase) for _ in range(16))}.{url}")

    if len(ips_1) > 0 or len(ips_2) > 0:
        log.debug("%s has wildcards enabled.", url)
        return True

    return False


def result_contains_canary(contents: List):
    return any("does_not_exist_canary" in row["name"] for row in contents)


@app.task(queue="storage")
def dnsrecon_parse_report_contents(contents: List, url: Dict[str, Any]):
    """
    [
        {'type': 'A', 'name': 'basisbeveiliging.nl', 'address': '1.1.1.1'},
        {'type': 'AAAA', 'name': 'basisbeveiliging.nl', 'address': '2a00:d00:ff:....'},
        {'type': 'A', 'name': 'something.somthing.something.darkside.example.com', 'address': 'no_ip'}
    ]
    """
    # If 'does_not_exist_canary' is returned as one of the subdomains, something went wrong in wildcard identification
    # so in that case just forget the entire result...

    if result_contains_canary(contents):
        return []

    addedlist = []
    # https://stackoverflow.com/questions/11328940/check-if-list-item-contains-items-fro
    # strings: dkim etc
    # target: cname
    # arguments: dnsrecon
    # ns_server: nameserver used
    bad = ["arguments", "ns_server", "mname", "Version", "exchange", "strings", "target"]
    for record in contents:
        # brutally ignore all kinds of info from other structures.
        log.debug("Record: %s", record)
        my_list = list(record.keys())
        if [e for e in bad if e in "\n".join(my_list)]:
            continue

        # "address": "no_ip",
        if record["address"] == "no_ip":
            continue

        if record["name"].endswith(url["url"]) and record["name"].lower() != url["url"].lower():
            subdomain = record["name"][: -len(url["url"]) - 1]
            # remove wildcards: "name": "*.woonsubsidie.amsterdam.nl",
            if subdomain[:2] == "*.":
                subdomain = subdomain[2:]

            # will check for resolve and if this is a wildcard.
            db_url = Url.objects.all().filter(pk=url["id"]).first()
            if not db_url:
                continue

            added = db_url.add_subdomain(subdomain.lower())
            if added:
                addedlist.append(added.url)

    return addedlist


# place it on the IPv4 queue, so it can scale using cloud workers :)
# It seems that a rate limited task blocks an entire worker for any other tasks.
@app.task(ignore_result=True, queue="known_subdomains")
def wordlist_scan(url: str, wordlist: List[str]):
    """
    60/h = 10.000 scans / week.

    :param url:
    :param wordlist:
    :return:
    """
    log.debug("Performing wordlist scan on %s, with the wordlist of %s words", url, len(wordlist))

    # any organization can determine at any points that there are now wildcards in effect
    # would we not check this, all urls below the current url will be seen as valid, which
    # results in database polution and a lot of extra useless scans.
    # You can't run remove_and_save_wildcards here as it needs access to storage.
    # urls_without_wildcards = remove_wildcards(urls)

    # Not checking for wildcards anymore, we're using a feature in dnsrecon to discern between the wildcard IP
    # and the rest of the IPs'. That works pretty well (not found a deviating case yet).

    # We still create the temporary file to have dnsrecon handle the meat and bugs with it's threadpool and other stuff
    log.debug("Creating temporary file from wordlist")
    with tempfile.NamedTemporaryFile(mode="wt") as tmp_wordlist:
        for word in wordlist:
            tmp_wordlist.write(f"{word}\n")
        tmp_wordlist.flush()  # make sure it's actually written.

        log.debug("The wordlist file is written as %s", tmp_wordlist.name)
        log.info("Wordlist scan on: %s", url)

        resolver = DnsHelper(url, [get_random_nameserver()], 3)
        # Using the filter option, only adds the addresses that don't go to the wildcard record.
        # In the logfile all dns responses are shown, but in the list of really resolving urls only the ones
        # that deviate from the wildcard IP are stored.
        found_hosts = brute_domain(resolver, tmp_wordlist.name, url, filter_=False, verbose=False, ignore_wildcard=True)

        # some hosts rotate a set of IP's when providing wildcards. This is an annoying practice.
        # We can filter those out with some statistics. We cut off everything that resolve to the top IP's.
        log.debug("Found %s hosts", len(found_hosts))
        found_hosts = remove_wildcards_using_statistics(found_hosts, url)

        # You cant' know how many where added, since you don't have access to storage.
        return found_hosts


def remove_wildcards_using_statistics(found_hosts, url: str):
    # todo: test
    # some hosts rotate a set of IP's when providing wildcards. This is an annoying practice.
    # We can filter those out with some statistics. We cut off everything that resolve to the top IP's.
    ip_stats = {}

    # if no wildcards are used, then well... just return everything as being fine
    if not discover_wildcard(url):
        return found_hosts

    # Create a list of how many IP's are used
    # dnsrecon filters out the first IP, so if there is only one wildcard IP, then that's that.
    for host in found_hosts:

        # Points to a A / AAAA record
        if "address" in host:
            if host["address"] not in ip_stats:
                ip_stats[host["address"]] = 1
            else:
                ip_stats[host["address"]] += 1

        # points to a certain CNAME
        if "target" in host:
            if host["target"] not in ip_stats:
                ip_stats[host["target"]] = 1
            else:
                ip_stats[host["target"]] += 1

    log.debug("Ip Stats")
    log.debug(ip_stats)
    return find_interesting_ips(ip_stats, found_hosts)


def find_interesting_ips(ip_stats, found_hosts):
    # block IP's that are being used more than 10 times. 10, because i like the number. More than 10 sites on
    # the same server? perfectly possible...
    banned_ips = [key for key in ip_stats if ip_stats[key] > 10]
    log.debug("Banned IPS")
    log.debug(banned_ips)

    interesting_found_hosts = []
    # remove all found hosts that are on the banned IP list:
    for host in found_hosts:

        if "address" in host and host["address"] not in banned_ips:
            interesting_found_hosts.append(host)

        if "target" in host and host["target"] not in banned_ips:
            interesting_found_hosts.append(host)

    log.debug("Interesting hosts")
    log.debug(interesting_found_hosts)

    return interesting_found_hosts


def remove_wildcards(urls: List[Url]):
    return [url for url in urls if not url_discover_wildcard(url)]


# don't overload the crt.sh service, rate limit
# rate limit is implemented in queue system, dont hard-code it in the worst way possible.
@app.task(queue="discover_subdomains")
def certificate_transparency_scan(url: str):
    """
    Checks the certificate transparency database for subdomains. Using a regex the subdomains
    are extracted. This method is extremely fast and reliable: these certificates all exist.

    Hooray for transparency :)
    :return:
    """

    # dumb rate limiting
    sleep(10)

    # https://crt.sh/?q=%25.zutphen.nl
    crt_sh_url = f"https://crt.sh/?q=%25.{url}"
    pattern = r"[^\s%>]*\." + url.replace(".", r"\.")

    try:
        response = requests.get(crt_sh_url, timeout=(300, 300), allow_redirects=False)
    except RequestException as e:
        log.error("crt.sh request failed: %s", e)
        return []

    matches = re.findall(pattern, response.text)

    subdomains = []
    for match in matches:
        # handle wildcards, sometimes subdomains have nice features.
        # examples: *.apps.domain.tld.
        # done: perhaps store that it was a wildcard cert, for further inspection?
        # - no we don't as that can change and this information can be outdated. We will check on that using any
        # brute force dns scan and some other places. Adding the logic here will increase complexity.
        match = match.replace("*.", "")
        if match != url:
            subdomains.append(match[: len(match) - len(url) - 1])  # wraps around

    subdomains = [x.lower() for x in subdomains]  # do lowercase normalization elsewhere
    subdomains = set(subdomains)

    # 25 and '' are created due to the percentage and empty subdomains. Remove them
    # wildcards (*) are also not allowed.
    if "" in subdomains:
        subdomains.remove("")
    if "25" in subdomains:
        subdomains.remove("25")

    log.debug("Found subdomains: %s", subdomains)
    # set is not json serializable
    return list(subdomains)


@app.task(queue="storage")
def store_certificate_transparency_results(subdomains: List[str], url_id: int) -> List[str]:
    if not subdomains:
        return []

    db_url = Url.objects.all().filter(id=url_id).first()
    if not db_url:
        return []

    addedlist: List[str] = []
    for subdomain in subdomains:
        if added := db_url.add_subdomain(subdomain):
            addedlist.append(added.url)

    return addedlist


# this is a fairly safe scanner, and can be run pretty quiclkly (no clue if parralelisation works)
@app.task(ignore_result=True, queue="discover_subdomains")
def nsec_scan(url: str):
    """
    Tries to use nsec (dnssec) walking. Does not use nsec3 (hashes).

    When nsec is used, all domains in the dns will be revealed, which is nice.

    Do note that it outputs records:

    - They might not be responding to ping, or have no services.
    - They do exist as a record: a wildcard domain....

    :param urls:
    :return:
    """
    try:
        # some DNS servers have infinite responses and loops when zone walking, do not get caught up in this...
        return nsec_scan_work(url)
    except TimeoutError:
        log.error("Timeout when nsec zone walking domain.", extra={"url": url})
        return []


@timeout(120, "Took too long to nsec zone walk, possibly an infinite loop.")
def nsec_scan_work(url: str):
    resolver = DnsHelper(url, [get_random_nameserver()], 3)
    return ds_zone_walk(resolver, url, 3)


def get_subdomains(countries: List, organization_types: List = None):
    urls = Url.objects.all()

    if countries:
        urls = urls.filter(organization__country__in=countries)

    if organization_types:
        urls = urls.filter(organization__type__name__in=organization_types)

    # make sure no queryset is returned
    return list(urls.values_list("computed_subdomain", flat=True).distinct().order_by("computed_subdomain"))


def get_popular_subdomains(country: str = "NL"):
    """
    Returns the domains that are used the most: some subdomains are used over and over because of popular vendors.
    Or just because of stupid luck.

    This saves a lot of guessing of subdomains that are unpopular. Because Django is hard to use in this case,
    we're using a plain and simple SQL query that works everywhere. Here is an overview of what you can expect. So
    you only have to find five to find the other hundred.

    +-----------------------------+--------+
    | computed_subdomain          | amount |
    +-----------------------------+--------+
    | www                         |   2631 |
    | autodiscover                |    439 |
    | mail                        |    418 |
    | webmail                     |    344 |
    | sip                         |    253 |
    | lyncdiscover                |    204 |
    | intranet                    |    184 |
    | digikoppeling               |    165 |
    | test                        |    153 |
    | iburgerzaken                |    151 |
    | portal                      |    150 |
    | ibzpink                     |    149 |
    | mijn                        |    141 |
    | simsite                     |    141 |
    | afspraken                   |    140 |
    | opendata                    |    138 |
    | vpn                         |    131 |
    | ftp                         |    129 |
    | adfs                        |    123 |
    | preproductie                |    118 |
    | feeds                       |    115 |
    | acceptatie                  |    114 |
    | secure                      |    105 |
    | enterpriseregistration      |    104 |
    | enterpriseenrollment        |     93 |
    | remote                      |     93 |
    | meet                        |     91 |
    | werkplek                    |     82 |
    | acc                         |     81 |
    | formulieren                 |     77 |
    | edienstenburgerzaken        |     76 |
    | edienstenburgerzaken-test   |     75 |
    | smtp                        |     68 |
    | sts                         |     68 |
    | geo                         |     66 |
    | mdm                         |     66 |
    | afspraak                    |     61 |
    | login                       |     60 |
    | loket                       |     60 |
    | simcms                      |     59 |
    | dialin                      |     55 |
    | a-www                       |     54 |
    | english                     |     51 |
    | a-opendata                  |     50 |
    | hybrid                      |     50 |
    ...
    +-----------------------------+--------+
    490 rows in set (0.20 sec)

    > 3 =
    > 2 = 1635
    > 1 = 2911 urls
    > 0 = 21535 urls

    Country and organization type have a lot of influence in this, as each have their own specific set of subdomains.
    Resulting in > 5 = 457 rows.
    """

    # some really basic validation to prevent injections and such
    country = get_country(country)

    # i'm _DONE_ with the obscuring of group_by and counts using terrible abstractions.
    # so here is a raw query that just works on all databases and is trivially simple to understand.
    # The popularity of a domain per country is still an unknown.
    sql = f"""SELECT
                 computed_subdomain, count(computed_subdomain) as amount
             FROM
                 url
             WHERE
                 url.is_dead=false
                 AND url.not_resolvable=false
                 AND url.computed_subdomain != ''
                 /* not making a carthesian product where a domain is used over and over. */
                 AND computed_subdomain in (
                    SELECT DISTINCT computed_subdomain FROM url
                    INNER JOIN url_organization on url_organization.url_id = url.id
                    INNER JOIN organization on url_organization.organization_id = organization.id
                    WHERE organization.is_dead=false
                    AND organization.country = '{country}'
                )
             GROUP BY
                 computed_subdomain
             /* No need to filter as a LIMIT is used, so this also works with very small datasets.
                but make sure no 'one shots' are added, as there will be a lot of those. */
             HAVING count(computed_subdomain) > 1
             ORDER BY count(computed_subdomain) DESC
             LIMIT 500
             """

    cursor = connection.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()

    subdomains: List[str] = [row[0] for row in rows]

    # add a nonsense subdomain that can be easily identified in the database in case something went wrong in
    # subdomain detection. Basically when this subdomain appears all other subdomains are probably also invalid.
    if subdomains:
        subdomains.append("does_not_exist_canary")

    return sorted(subdomains)


def make_threeletter_wordlist():
    alphabets = [
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g",
        "h",
        "i",
        "j",
        "k",
        "l",
        "m",
        "n",
        "o",
        "p",
        "q",
        "r",
        "s",
        "t",
        "u",
        "v",
        "w",
        "x",
        "y",
        "z",
    ]
    threeletters = ["".join(i) for i in itertools.product(alphabets, repeat=3)]
    twoletters = ["".join(i) for i in itertools.product(alphabets, repeat=2)]

    return alphabets + threeletters + twoletters

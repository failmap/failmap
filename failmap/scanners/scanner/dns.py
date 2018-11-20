import builtins
import itertools
import logging
import random
import string
import subprocess
import sys
import tempfile
from datetime import datetime
from typing import List

import pytz
import untangle
from celery import Task, group
from django.conf import settings
from tenacity import before_log, retry, wait_fixed

from failmap.celery import app
from failmap.organizations.models import Organization, Url
from failmap.scanners.scanner.http import get_ips
from failmap.scanners.scanner.scanner import (allowed_to_discover, q_configurations_to_scan,
                                              url_filters)

"""
Performs a range of DNS scans:
- Using Search engines
- Using Wordlists
- Using Certificate Transparency
- Using NSEC

It separates the scans as it might be desirable to use different scanners.

Todo: the list of known subdomains might help (a lot) with breaking nsec3 hashes?
https://github.com/anonion0/nsec3map

"""
# todo: if ScannerHttp.has_internet_connection():


sys.path.append(settings.VENDOR_DIR + '/dnsrecon/')

log = logging.getLogger(__package__)

theharvester = settings.TOOLS['theHarvester']['executable']
dnsrecon = settings.TOOLS['dnsrecon']['executable']

# the length is used for checking wildcards, dnsrecon doesn't always does that right.
# if the returned list of domains is about as long as the wordlist... then it's a wildcard
# except if the wordlist is very small.
wordlists = {
    'dutch_basic': {
        'path': settings.TOOLS['dnsrecon']['wordlist_dir'] + "OpenTaal-210G-basis-gekeurd.txt",
        'length': 180000
    },
    # organizations _LOVE_ three letter acronyms! I mean TLA's! :)
    # Let's call the Anti Acronym Association of America.
    'three_letters': {
        'path': settings.TOOLS['dnsrecon']['wordlist_dir'] + "threeletterwordlist.txt",
        'length': 18000
    },
    'known_subdomains': {
        'path': settings.TOOLS['dnsrecon']['wordlist_dir'] + "knownsubdomains.txt",
        'length': 200
    },
    # We want to know if a domain uses wildcards, and also store it. So dnsrecon might be suited
    # for this, it doesn't output if a url has wildcard support.
    'nonsense': {
        'path': settings.TOOLS['dnsrecon']['wordlist_dir'] + "nonsense.txt",
        'length': 2
    }
}


"""
It is possible an organization does not use their tld, but a subdomain.
For example: www.example.com might resolve but example.com doesn't.

It's very convenient to add non-existing top-level domains, as that is a starting point for dns scans.
"""


def search_engines(organizations: List[Organization] = None, urls: List[Url] = None):
    urls = toplevel_urls(organizations=organizations) if organizations else [] + urls if urls else []
    return [new_url for new_url in search_engines_scan(urls)]


def nsec(organizations: List[Organization] = None, urls: List[Url] = None):
    urls = toplevel_urls(organizations=organizations) if organizations else [] + urls if urls else []
    return [new_url for new_url in nsec_scan(urls)]


def url_by_filters(organizations_filter: dict = dict(), urls_filter: dict = dict(),
                   endpoints_filter: dict = dict()) -> List:
    if endpoints_filter:
        raise NotImplementedError("Endpoints are not yet supported for DNS scans.")

    # todo: check voor toplevel
    # todo: functional decomposition

    # merge
    toplevel_filter = {"computed_subdomain": ""}

    # merge using python 3.6 syntax
    # https://stackoverflow.com/questions/38987/how-to-merge-two-dictionaries-in-a-single-expression
    urls_filter = {**toplevel_filter, **urls_filter}

    # urls = Url.objects.all()
    urls = Url.objects.all().filter(q_configurations_to_scan(level='url'), **urls_filter)

    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter)
        # when empty no results.
        urls = urls.filter(organization__in=organizations, **urls_filter)
    else:
        urls = urls.filter(**urls_filter)

    return list(urls)


def nsec_compose_task(organizations_filter: dict = dict(),
                      urls_filter: dict = dict(),
                      endpoints_filter: dict = dict(), **kwargs) -> Task:

    if not allowed_to_discover("nsec_compose_task"):
        return group()

    urls = url_by_filters(organizations_filter=organizations_filter,
                          urls_filter=urls_filter,
                          endpoints_filter=endpoints_filter)

    task = group(nsec_scan.si([url]) for url in urls)
    return task


def certificate_transparency(organizations: List[Organization] = None, urls: List[Url] = None):
    urls = toplevel_urls(organizations=organizations) if organizations else [] + urls if urls else []
    return [new_url for new_url in certificate_transparency_scan(urls)]


def certificate_transparency_compose_task(organizations_filter: dict = dict(),
                                          urls_filter: dict = dict(),
                                          endpoints_filter: dict = dict(), **kwargs) -> Task:

    if not allowed_to_discover("certificate_transparency_compose_task"):
        return group()

    urls = url_by_filters(organizations_filter=organizations_filter,
                          urls_filter=urls_filter,
                          endpoints_filter=endpoints_filter)

    task = group(certificate_transparency_scan.si([url]) for url in urls)
    return task


def compose_discover_task(organizations_filter: dict = dict(),
                          urls_filter: dict = dict(),
                          endpoints_filter: dict = dict(), **kwargs) -> Task:

    # these approaches have the highest chance of getting new subdomains.
    if not allowed_to_discover("certificate_transparency_compose_task"):
        log.info("Not allowed to scan for certificate_transparency")
        return group()

    if not allowed_to_discover("nsec_compose_task"):
        log.info("Not allowed to scan for nsec")
        return group()

    urls = url_by_filters(organizations_filter=organizations_filter,
                          urls_filter=urls_filter,
                          endpoints_filter=endpoints_filter)

    if not urls:
        log.debug('No urls found for subdomain discovery.')

    task = group(certificate_transparency_scan.si([url]) | nsec_scan.si([url]) for url in urls)
    return task


# it will not revive anything(!) Should that be a revive task?
def compose_verify_task(organizations_filter: dict = dict(),
                        urls_filter: dict = dict(),
                        endpoints_filter: dict = dict(), **kwargs) -> Task:

    # instead of only checking by domain, just accept the filters as they are handled in any other scenario...

    default_filter = {"not_resolvable": False}
    urls_filter = {**urls_filter, **default_filter}

    urls = Url.objects.all().filter(q_configurations_to_scan(level='url'))
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)

    if not urls:
        log.debug('No urls found for (sub)domain verification.')

    log.info("Will verify DNS resolvability of %s urls" % len(urls))

    task = group(url_resolves.si(url) | handle_resolves.s(url) for url in urls)
    return task


# this is so fast, the overhead on running this elsewhere is insane... requires both ipv4 and 6 capabilities
@app.task(queue="internet")
def url_resolves(url):

    v4, v6 = get_ips(url.url)

    if not v4 and not v6:
        return False

    return True


@app.task(queue="storage")
def handle_resolves(resolves, url):

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


def brute_dutch(organizations: List[Organization] = None, urls: List[Url] = None):
    urls = toplevel_urls_without_wildcards(organizations) if organizations else [] + urls if urls else []
    return wordlist_scan_old(urls, str(wordlists["dutch_basic"]["path"]))


def brute_three_letters(organizations: List[Organization] = None, urls: List[Url] = None):
    urls = toplevel_urls_without_wildcards(organizations) if organizations else [] + urls if urls else []
    return wordlist_scan_old(urls, str(wordlists["three_letters"]["path"]))


def standard(organizations: List[Organization] = None, urls: List[Url] = None):
    """
    Runs scans that are not heavy and potentially return a lot of results:

    certificate_transparency: 1 request results dozens of urls
    nsec: a few dns requests deliver all subdomains there are out there for a domain

    not used:
    search_engine: this requires a search engine scan and cannot be bulk-automated due to rate limiting
    brute_force:

    :param organizations:
    :param urls:
    :return:
    """

    certificate_transparency(organizations=organizations, urls=urls)
    nsec(organizations=organizations, urls=urls)


def toplevel_urls(organizations):
    return Url.objects.all().filter(organization__in=organizations,
                                    computed_subdomain="")


# This helps to determine at database level if the DNS uses wildcards, so it can be dealt
# with in another way.
def toplevel_urls_without_wildcards(organizations: List):
    return Url.objects.all().filter(organization__in=organizations,
                                    computed_subdomain="",
                                    uses_dns_wildcard=False)


def remove_and_save_wildcards(urls: List[Url]):
    without_wildcards, with_wildcards = has_wildcards(urls)
    return without_wildcards


def has_wildcards(urls: List[Url]):
    """ Run this when adding a new url.

    So you can be sure that there are no wildcards if you don't want them.

    Of course the DNS can change every day, so you never know for sure.
    """

    urls_with_wildcards = []
    urls_without_wildcards = []

    for url in urls:
        if url_discover_wildcard(url):
            log.info("Domain %s uses wildcards, DNS brute force not possible" % url.url)
            url.uses_dns_wildcard = True
            url.save()
            urls_with_wildcards.append(url)
        else:
            url.uses_dns_wildcard = False
            url.save()
            urls_without_wildcards.append(url)

    log.debug("Of the %s urls, %s had a wildcard and %s did not." % (len(urls), len(urls_with_wildcards),
                                                                     len(urls_without_wildcards)))

    return urls_without_wildcards, urls_with_wildcards


def url_discover_wildcard(url: Url):
    """
    We need to perform a check ourselves, since we cannot get from the DNSRecon report if the url
    uses wildcards. We store this ourselves so we can better filter domains.

    In some cases DNSrecon makes a wrong assumption about wildcard usage. This is hopefully a bit better.
    """
    # import DNSRecon using evil methods
    sys.path.append(settings.VENDOR_DIR + '/dnsrecon/')
    from lib.dnshelper import DnsHelper

    log.debug("Checking for DNS wildcards on domain: %s" % url.url)

    wildcard = False

    resolver = DnsHelper(url.url, get_random_dns_ip(), 3)

    # Do this test twice, there are dns servers that say NO the first time, but say yes the second (i mean wtf)
    ips_1 = resolver.get_a("%s.%s" % (''.join(random.choice(string.ascii_lowercase) for i in range(16)), url.url))
    ips_2 = resolver.get_a("%s.%s" % (''.join(random.choice(string.ascii_lowercase) for i in range(16)), url.url))

    if len(ips_1) > 0 or len(ips_2) > 0:
        log.debug("%s has wildcards enabled." % url.url)
        return True

    return wildcard


def import_dnsrecon_report(url: Url, path: str):
    # note: the order of the records in the report matters(!)
    import json
    with open(path) as data_file:
        data = json.load(data_file)
        addedlist = dnsrecon_parse_report_contents(url, data)
    return addedlist


@app.task(queue="storage")
def dnsrecon_parse_report_contents(url: Url, contents: List):
    addedlist = []
    for record in contents:
        # brutally ignore all kinds of info from other structures.
        log.debug("Record: %s" % record)
        # https://stackoverflow.com/questions/11328940/check-if-list-item-contains-items-fro
        # strings: dkim etc
        # target: cname
        # arguments: dnsrecon
        # ns_server: nameserver used
        bad = ["arguments", "ns_server", "mname", "Version", "exchange", "strings", "target"]
        my_list = list(record.keys())
        if [e for e in bad if e in '\n'.join(my_list)]:
            continue

        # "address": "no_ip",
        if record["address"] == "no_ip":
            continue

        if record["name"].endswith(url.url) and record["name"].lower() != url.url.lower():
            subdomain = record["name"][0:-len(url.url) - 1]
            # remove wildcards: "name": "*.woonsubsidie.amsterdam.nl",
            if subdomain[0:2] == "*.":
                subdomain = subdomain[2:len(subdomain)]

            # will check for resolve and if this is a wildcard.
            added = url.add_subdomain(subdomain.lower())
            if added:
                addedlist.append(added)

    return addedlist


def search_engines_scan(urls: List[Url]):
    """
    :param urls: List[Url]
    :return: List[Url]
    """
    addedlist = []
    for url in urls:
        # Todo: sometimes the report contains subdomains for other organizations at top level domain: add these also
        # Searching the internet for subdomains might result in overly long and incorrect lists.
        # The only correct way is to curate domains by hand.
        # So, we should also try to import those. So we have maximum result from our scan.
        log.info("Harvesting DNS of toplevel domain: %s" % url.url)
        log.warning("Search engines have strict rate limiting, do not use this function in an "
                    "automated scan.")
        # a bug in the harvester breaks the file at the first dot and uses that as the xml file,
        # and the full filename as the html file.
        file = ("%s_harvester_all" % url.url).replace(".", "_") + ".xml"
        path = settings.TOOLS['theHarvester']['output_dir'] + file

        log.debug("DNS results will be stored in file: %s" % path)
        engine = "all"
        subprocess.call(['python', theharvester,
                         '-d', url.url,
                         '-b', engine,
                         '-s', '0',
                         '-l', '100',
                         '-f', path])

        # read XML file, extract hosts + vhosts (both can contain the url).
        # explicitly search for .toplevel.nl (with leading dot) to not find .blatoplevel.nl
        subdomains = []
        obj = untangle.parse(path)
        hosts = []
        if hasattr(obj.theHarvester, 'host'):
            hosts += [host for host in obj.theHarvester.host]

        if hasattr(obj.theHarvester, 'vhost'):
            hosts += [host for host in obj.theHarvester.vhost]

        for host in hosts:
            hostname = host.hostname.cdata
            log.debug("Hostname: %s" % hostname)
            if hostname.endswith("." + url.url):
                subdomains.append(hostname[0:len(hostname) - len(url.url) - 1])
                log.debug("Subdomain: %s" % hostname[0:len(hostname) - len(url.url) - 1])

        subdomains = [x.lower() for x in subdomains]
        subdomains = set(subdomains)  # only unique

        log.debug("Found subdomains: %s" % subdomains)

        for subdomain in subdomains:
            added = url.add_subdomain(subdomain)
            if added:
                addedlist.append(added)
    return addedlist


# place it on the IPv4 queue, so it can scale using cloud workers :)
@app.task(ignore_result=True, queue="ipv4", rate_limit='6/h')
def wordlist_scan(urls: List[Url], wordlist: List[str]):
    """

    :param urls:
    :param wordlist:
    :return:
    """
    # import DNSRecon using evil methods
    sys.path.append(settings.VENDOR_DIR + '/dnsrecon/')
    from lib.dnshelper import DnsHelper
    from dnsrecon import ThreadPool, brute_domain

    # dnsrecon needs it's own threadpool. And you can only override it via builtins.
    global pool
    pool = ThreadPool(10)
    # globals()['pool'] = pool
    builtins.pool = pool

    # overwrite readline to always return "n", to handle any UI calls from dnsrecon.
    # So even if our wildcard check fails, which happens sometimes, there is still the fallback in DNSRecon.
    sys.stdin.readline = always_no

    log.debug("Performing wordlist scan on %s urls, with the wordlist of %s words" % (len(urls), len(wordlist)))

    # any organization can determine at any points that there are now wildcards in effect
    # would we not check this, all urls below the current url will be seen as valid, which
    # results in database polution and a lot of extra useless scans.
    # You can't run remove_and_save_wildcards here as it needs access to storage.
    urls_without_wildcards = remove_wildcards(urls)

    if not urls_without_wildcards:
        log.debug("No urls found without wildcards.")
        return []

    # We still create the temporary file to have dnsrecon handle the meat and bugs with it's threadpool and other stuff
    log.debug("Creating temporary file from wordlist")
    with tempfile.NamedTemporaryFile(mode="wt") as tmp_wordlist:
        for word in wordlist:
            tmp_wordlist.write("%s\n" % word)
        tmp_wordlist.flush()  # make sure it's actually written.

        log.debug("The wordlist file is written as %s" % tmp_wordlist.name)

        imported_urls = []
        for url in urls_without_wildcards:
            log.info("Wordlist scan on: %s" % url.url)

            resolver_ip = get_random_dns_ip()
            log.debug("Using the DNS service from %s" % resolver_ip)
            resolver = DnsHelper(url.url, resolver_ip, 3)
            found_hosts = brute_domain(resolver, tmp_wordlist.name, url.url, None, verbose=False)

            log.debug("Found %s hosts" % len(found_hosts))

            # You cant' know how many where added, since you don't have access to storage.
            dnsrecon_parse_report_contents.apply_async([url, found_hosts], queue="storage")

    log.debug("Wordlist scan(s) finished.")

    return imported_urls


def always_no(message=""):
    return "n"


def remove_wildcards(urls: List[Url]):

    urls_without_wildcards = []
    for url in urls:
        if not url_discover_wildcard(url):
            urls_without_wildcards.append(url)

    return urls_without_wildcards


def get_random_dns_ip():
    """
    Using one of the public and popular DNS services.

    :return:
    """

    # 1.0.0.1 == 1.1.1.1 (cloudflare)
    # 8.8.4.4 == 8.8.8.8 (google)
    # 199.85.127.10 == 199.85.126.10 (norton), no norton for us, because norton.
    # 8.26.56.26 == 8.20.247.20 (comodo)
    # 149.112.112.112 == 9.9.9.9 (quad9)

    return random.choice(['1.1.1.1', '9.9.9.9', '8.8.8.8', '8.26.56.26'])


# this can be highly invasive and slow, so try to behave: rate limit: 1 to 2 per minute.
@app.task(ignore_result=True, queue="internet", rate_limit='40/h')
def wordlist_scan_old(urls: List[Url], wordlist: str):
    """

    :param urls:
    :param wordlist:
    :return:
    """

    # any organization can determine at any points that there are now wildcards in effect
    # would we not check this, all urls below the current url will be seen as valid, which
    # results in database polution and a lot of extra useless scans.
    urls = remove_and_save_wildcards(urls)

    imported_urls = []
    for url in urls:
        log.info("Bruting DNS of toplevel domain: %s" % url.url)
        log.debug("Using wordlist: %s" % wordlist)
        file = "%s_data_brute.json" % url.url
        path = settings.TOOLS['dnsrecon']['output_dir'] + file

        log.debug("DNS results will be stored in file: %s" % path)

        # never continue with wildcard domains
        p = subprocess.Popen(['python', dnsrecon,
                              '--domain', url.url,
                              '-t', 'brt',
                              '-D', wordlist,
                              '-j', path], stdin=subprocess.PIPE)
        p.stdin.write('n'.encode(encoding='utf-8'))
        p.stdin.write('n'.encode(encoding='utf-8'))
        p.stdin.write('n'.encode(encoding='utf-8'))
        p.stdin.write('n'.encode(encoding='utf-8'))
        p.stdin.write('n'.encode(encoding='utf-8'))
        p.stdin.write('n'.encode(encoding='utf-8'))  # never brute a wildcard,
        # The above input doens't always work it seems...
        p.communicate()

        imported_urls += import_dnsrecon_report(url, path)

    return imported_urls


# don't overload the crt.sh service, rate limit
# todo: create a generic: go to $page with $parameter and scrape all urls.
@app.task(ignore_result=True, queue="internet", rate_limit='2/m')
@retry(wait=wait_fixed(30), before=before_log(log, logging.INFO))
def certificate_transparency_scan(urls: List[Url]):
    """
    Checks the certificate transparency database for subdomains. Using a regex the subdomains
    are extracted. This method is extremely fast and reliable: these certificates all exist.

    Hooray for transparency :)

    :param urls: List of Url objects
    :return:
    """
    import requests
    import re

    addedlist = []
    for url in urls:

        # https://crt.sh/?q=%25.zutphen.nl
        crt_sh_url = "https://crt.sh/?q=%25." + str(url.url)
        pattern = r"[^\s%>]*\." + str(url.url.replace(".", "\."))  # harder string formatting :)

        response = requests.get(crt_sh_url, timeout=(10, 10), allow_redirects=False)
        matches = re.findall(pattern, response.text)

        subdomains = []
        for match in matches:
            # handle wildcards, sometimes subdomains have nice features.
            # examples: *.apps.domain.tld.
            # done: perhaps store that it was a wildcard cert, for further inspection?
            # - no we don't as that can change and this information can be outdated. We will check on that using any
            # brute force dns scan and some other places. Adding the logic here will increase complexity.
            match = match.replace("*.", "")
            if match != url.url:
                subdomains.append(match[0:len(match) - len(url.url) - 1])  # wraps around

        subdomains = [x.lower() for x in subdomains]  # do lowercase normalization elsewhere
        subdomains = set(subdomains)

        # 25 and '' are created due to the percentage and empty subdomains. Remove them
        # wildcards (*) are also not allowed.
        if '' in subdomains:
            subdomains.remove('')
        if '25' in subdomains:
            subdomains.remove('25')

        log.debug("Found subdomains: %s" % subdomains)

        for subdomain in subdomains:
            added = url.add_subdomain(subdomain)
            if added:
                addedlist.append(added)
    return addedlist


# this is a fairly safe scanner, and can be run pretty quiclkly (no clue if parralelisation works)
@app.task(ignore_result=True, queue="internet", rate_limit='4/m')
def nsec_scan(urls: List[Url]):
    """
    Tries to use nsec (dnssec) walking. Does not use nsec3 (hashes).

    When nsec is used, all domains in the dns will be revealed, which is nice.

    Do note that it outputs records:

    - They might not be responding to ping, or have no services.
    - They do exist as a record: a wildcard domain....

    :param urls:
    :return:
    """
    # import DNSRecon using evil methods
    sys.path.append(settings.VENDOR_DIR + '/dnsrecon/')
    from lib.dnshelper import DnsHelper
    from dnsrecon import ds_zone_walk

    for url in urls:
        resolver = DnsHelper(url.url, '8.8.8.8', 30)
        records = ds_zone_walk(resolver, url.url)
        log.info(records)
        dnsrecon_parse_report_contents.apply_async([url, records])
        # return


def get_subdomains(countries: List, organization_types: List = None):
    urls = Url.objects.all()

    if countries:
        urls = urls.filter(organization__country__in=countries)

    if organization_types:
        urls = urls.filter(organization__type__name__in=organization_types)

    return urls.values_list('computed_subdomain', flat=True).distinct()


def make_threeletter_wordlist():
    alphabets = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p',
                 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']
    threeletters = [''.join(i) for i in itertools.product(alphabets, repeat=3)]
    twoletters = [''.join(i) for i in itertools.product(alphabets, repeat=2)]

    return alphabets + threeletters + twoletters

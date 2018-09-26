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
# todo: language matters, many of the NL subdomains don't make sense in other countries.

import itertools
import logging
import random
import string
import subprocess
from typing import List

import untangle
from celery import Task, group
from django.conf import settings

from failmap.celery import app
from failmap.organizations.models import Organization, Url
from failmap.scanners.scanner.scanner import allowed_to_discover

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

    urls = []
    # todo: check voor toplevel
    # todo: functional decomposition

    # merge
    toplevel_filter = {"computed_subdomain": ""}

    # merge using python 3.6 syntax
    # https://stackoverflow.com/questions/38987/how-to-merge-two-dictionaries-in-a-single-expression
    urls_filter = {**toplevel_filter, **urls_filter}

    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter)
        # when empty no results.
        urls += Url.objects.filter(organization__in=organizations, **urls_filter)
    else:
        urls += Url.objects.filter(**urls_filter)

    return urls


@app.task(ignore_result=True, queue="scanners")
def nsec_compose_task(organizations_filter: dict = dict(),
                      urls_filter: dict = dict(),
                      endpoints_filter: dict = dict(),) -> Task:

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


@app.task(ignore_result=True, queue="scanners")
def certificate_transparency_compose_task(organizations_filter: dict = dict(),
                                          urls_filter: dict = dict(),
                                          endpoints_filter: dict = dict(),) -> Task:

    if not allowed_to_discover("certificate_transparency_compose_task"):
        return group()

    urls = url_by_filters(organizations_filter=organizations_filter,
                          urls_filter=urls_filter,
                          endpoints_filter=endpoints_filter)

    task = group(certificate_transparency_scan.si([url]) for url in urls)
    return task


@app.task(ignore_result=True, queue="scanners")
def compose_discover_task(organizations_filter: dict = dict(),
                          urls_filter: dict = dict(),
                          endpoints_filter: dict = dict(),) -> Task:

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


def brute_dutch(organizations: List[Organization] = None, urls: List[Url] = None):
    urls = toplevel_urls_without_wildcards(organizations) if organizations else [] + urls if urls else []
    return bruteforce_scan(urls, str(wordlists["dutch_basic"]["path"]))


def brute_three_letters(organizations: List[Organization] = None, urls: List[Url] = None):
    urls = toplevel_urls_without_wildcards(organizations) if organizations else [] + urls if urls else []
    return bruteforce_scan(urls, str(wordlists["three_letters"]["path"]))


def brute_known_subdomains(organizations: List[Organization] = None, urls: List[Url] = None):
    if organizations:
        for organization in organizations:
            update_subdomain_wordlist()
            urls = toplevel_urls_without_wildcards(organization)
            return bruteforce_scan(urls, str(wordlists["known_subdomains"]["path"]))

    if urls:
        # this list of subdomains can be extended per url
        for url in urls:
            update_subdomain_wordlist()
            return bruteforce_scan([url], str(wordlists["known_subdomains"]["path"]))


@app.task(ignore_result=True, queue="scanners")
def brute_known_subdomains_compose_task(organizations_filter: dict = dict(),
                                        urls_filter: dict = dict(),
                                        endpoints_filter: dict = dict(),) -> Task:

    if not allowed_to_discover("brute_known_subdomains_compose_task"):
        return group()

    urls = url_by_filters(organizations_filter=organizations_filter,
                          urls_filter=urls_filter,
                          endpoints_filter=endpoints_filter)

    # todo: this should be placed to elsewhere, but we might not have write permissions in scanners...???
    update_subdomain_wordlist()

    task = group(bruteforce_scan.si([url], str(wordlists["known_subdomains"]["path"])) for url in urls)
    return task


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


def dnsrecon_default(urls):
    raise NotImplementedError
    # todo: Expanding IP ranges found in DNS and TXT records for Reverse Look-up takes ages.
    # This is due to expansion of IPv6 addresses, which is extreme and sometimes impossible
    # Since dnsrecon doesn't give the option to time-out or skip this expansion...
    # so no std for us :'( - or timeout this method (and skipping meaningful results) or patch
    # dnsrecon.
    # This doesn't ask google, the harvester is a bit more smarter / advanced.
    imported_urls = []
    for url in urls:
        log.info("Scanning DNS of toplevel domain: %s" % url.url)
        file = "%s_data_default.json" % url.url
        path = settings.TOOLS['dnsrecon']['output_dir'] + file

        log.debug("DNS results will be stored in file: %s" % path)

        # never continue with wildcard domains
        p = subprocess.Popen(['python', dnsrecon,
                              '--type', '"rvl,srv,axfr,snoop,zonewalk"'
                              '--domain', url.url,
                              '-j', path], stdin=subprocess.PIPE)
        p.stdin.write('n'.encode(encoding='utf-8'))
        p.stdin.write('n'.encode(encoding='utf-8'))
        p.stdin.write('n'.encode(encoding='utf-8'))
        p.stdin.write('n'.encode(encoding='utf-8'))
        p.stdin.write('n'.encode(encoding='utf-8'))
        p.stdin.write('n'.encode(encoding='utf-8'))  # never brute a wildcard,
        # The above input doens't always work it seems...
        p.communicate()

        imported_urls = imported_urls + import_dnsrecon_report(url, path)

    return imported_urls


def toplevel_urls(organizations):
    return Url.objects.all().filter(organization__in=organizations,
                                    computed_subdomain="")


# This helps to determine at database level if the DNS uses wildcards, so it can be dealt
# with in another way.
def toplevel_urls_without_wildcards(organizations):
    return Url.objects.all().filter(organization__in=organizations,
                                    computed_subdomain="",
                                    uses_dns_wildcard=False)


def remove_wildcards(urls: List[Url]):
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
        if discover_wildcard_scan(url):
            log.info("Domain %s uses wildcards, DNS brute force not possible" % url.url)
            url.uses_dns_wildcard = True
            url.save()
            urls_with_wildcards.append(url)
        else:
            url.uses_dns_wildcard = False
            url.save()
            urls_without_wildcards.append(url)

    return urls_without_wildcards, urls_with_wildcards


def discover_wildcard_scan(url: Url):
    """
    We need to perform a check ourselves, since we cannot get from the DNSRecon report if the url
    uses wildcards. We store this ourselves so we can better filter domains.

    In some cases DNSrecon makes a wrong assumption about wildcard usage. This is hopefully a bit better.
    """
    log.debug("Checking for DNS wildcards on domain: %s" % url.url)
    file = "%s_data_wildcards.json" % url.url
    path = settings.TOOLS['dnsrecon']['output_dir'] + file

    log.debug("DNS results will be stored in file: %s" % path)

    # never continue with wildcard domains
    # solving https://sentry.io/internet-cleanup-foundation/faalkaart/issues/467465408/
    randomize_nonsense_subdomains_wordlist()
    command = ['python', dnsrecon,
               '--domain', url.url,
               '-t', 'brt',
               '--iw',  # --iw: # always try wild card domains.
               '-D', wordlists["nonsense"]["path"],
               '-j', path]

    subprocess.check_output(command)

    import json
    wildcard = False
    with open(path) as data_file:
        data = json.load(data_file)
        for record in data:
            if "arguments" in record.keys():
                continue

            if record["name"].endswith(url.url):
                wildcard = True

    return wildcard


def import_dnsrecon_report(url: Url, path: str):
    # note: the order of the records in the report matters(!)
    import json
    with open(path) as data_file:
        data = json.load(data_file)
        addedlist = []
        for record in data:
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


# this can be highly invasive and slow, so try to behave: rate limit: 1 to 2 per minute.
@app.task(ignore_result=True, queue="scanners", rate_limit='40/h')
def bruteforce_scan(urls: List[Url], wordlist: str):
    """

    :param urls:
    :param wordlist:
    :return:
    """

    # any organization can determine at any points that there are now wildcards in effect
    # would we not check this, all urls below the current url will be seen as valid, which
    # results in database polution and a lot of extra useless scans.
    urls = remove_wildcards(urls)

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
@app.task(ignore_result=True, queue="scanners", rate_limit='10/m')
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
@app.task(ignore_result=True, queue="scanners", rate_limit='4/m')
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
    added = []
    for url in urls:
        file = settings.TOOLS['dnsrecon']['output_dir'] + "%s_nsec.json" % url.url
        command = ['python', dnsrecon, '-t', 'zonewalk', '-d', url.url, '-z', '-j', file]
        try:
            subprocess.check_output(command)
            added += import_dnsrecon_report(url, file)
        except subprocess.CalledProcessError as message:
            """
                If the first nameserver is borken:

                dns.resolver.NoNameservers: All nameservers failed to answer the query .
                IN A: Server 8.8.8.8 UDP port 53 answered SERVFAIL

                ns2 might still work.

            or

              File "dnshelper.py", line 197, in get_soa
                for rdata in answers:
                    UnboundLocalError: local variable 'answers' referenced before assignment
            """
            log.error('DNSRecon process error: %s' % str(message))

    return added


def update_subdomain_wordlist():
    # todo: per branche wordlists, more to the point
    prefixes = []
    urls = Url.objects.all()
    for url in urls:
        positions = [pos for pos, char in enumerate(url.url) if char == '.']
        if len(positions) > 1:
            prefixes.append(url.url[0:positions[len(positions) - 2]])
    # print(set(prefixes))
    unique_prefixes = set(prefixes)

    with open(str(wordlists["known_subdomains"]["path"]), "w") as text_file:
        for unique_prefix in unique_prefixes:
            text_file.write(unique_prefix + '\n')

    return unique_prefixes


def make_threeletter_wordlist():
    alphabets = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p',
                 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']
    threeletters = [''.join(i) for i in itertools.product(alphabets, repeat=3)]
    twoletters = [''.join(i) for i in itertools.product(alphabets, repeat=2)]

    with open("threeletterwordlist.txt", "w") as text_file:

        for x in alphabets:
            text_file.write(x + '\n')
        for x in threeletters:
            text_file.write(x + '\n')
        for x in twoletters:
            text_file.write(x + '\n')

# the chance of getting one or both domains back as existing is one in gazillions.
# but for the astronomically small chance there is another factor of gazillions.


def randomize_nonsense_subdomains_wordlist():
    letters = string.ascii_lowercase
    words = [''.join(random.choice(letters) for i in range(10)),
             ''.join(random.choice(letters) for i in range(10))]

    with open(wordlists["nonsense"]["path"], "w") as text_file:
        for word in words:
            text_file.write(word + '\n')

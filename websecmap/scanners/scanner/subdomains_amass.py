"""
Amass is an extensive subdomain discovery tool. It supports over 45 sources for subdomains.

For a single domain scan, it commonly uses 650 megabytes of ram and 100% cpu on one core. This means it will perform
it's scan slowly. You can use some resolvers to speed things up, but it still will be ridiculously slow.

Adding more domains means more times that 600 megabytes. So you can only do one domain at a time. The time needed
to complete a scan goes up to hours. This is not acceptable as we need to know how many domains are being scanned over
time. A year has 8000 hours. So with 2 hours per scan we do 4000 domains per year which is ridiculously slow.
Using more domains in a single scan does not necessarily mean that the scan will go any faster.

8000 hours = 480.000 minutes. So a timeout of 10 minutes makes this to 48.000 scans a year. For 3k domains you need
30000 minutes = 500 hours = 21 days. So that is pretty nice.

Starting a scan will cause complete lockdown of your system for seconds. It's really lagging everything.

Memory / cpu usage benchmark on an m1max:
Command: amass enum --nolocaldb -active -src -include crtsh,radb -d internet.nl
Ram: 630 megabytes
CPU: 100%

Command: amass enum -trf resolvers.txt --nolocaldb -active  -d internet.nl -d ey.com
Ram: 850 megabytes
CPU: 100%

Each organization means +250 meg of ram required.

Command: amass enum -trf resolvers.txt --nolocaldb -active  -d internet.nl -max-dns-queries 1000
Speed: ...


Parameter documentation:

-passive: only get list from datasource, doesn't validate if results exist which is not usable
normal (no param): taking names, resolving their ip's, no direct traffic to target organization
-active: retrieve names from certificates from target organization, also attempt (usually useless zone transfers)


-nolocaldb: do not store the results to the bolt graph database. This means no tracking, no visualistaion, etc. This
is fine in our workflow.

-trf = trusted resolvers file
-max-dns-queries = the speed of requests sent to dns resolvers. The default is 1000. A scan will run notably faster
when increasing this number to 10000. This increases the need for more resolvers.
 == -dns-qps

-json <outfile> writes the results to an outfile. This has to be a certain scan id to so we know what's what.

todo: check if we should use untrusted resolvers as well..

amass enum -trf resolvers.txt --nolocaldb -active -dns-qps 1000 -timeout 10 -json internetnl.json -d internet.nl

Scraping will probably be halted when running thousands of domains.

These tasks below will be used in the internet.nl dashboard subdomaindescoveryscan scanner...


Mandatory watching: https://www.youtube.com/watch?v=H1wdBgY1rtg

amass enum --help

        .+++:.            :                             .+++.
      +W@@@@@@8        &+W@#               o8W8:      +W@@@@@@#.   oW@@@W#+
     &@#+   .o@##.    .@@@o@W.o@@o       :@@#&W8o    .@#:  .:oW+  .@#+++&#&
    +@&        &@&     #@8 +@W@&8@+     :@W.   +@8   +@:          .@8
    8@          @@     8@o  8@8  WW    .@W      W@+  .@W.          o@#:
    WW          &@o    &@:  o@+  o@+   #@.      8@o   +W@#+.        +W@8:
    #@          :@W    &@+  &@+   @8  :@o       o@o     oW@@W+        oW@8
    o@+          @@&   &@+  &@+   #@  &@.      .W@W       .+#@&         o@W.
     WW         +@W@8. &@+  :&    o@+ #@      :@W&@&         &@:  ..     :@o
     :@W:      o@# +Wo &@+        :W: +@W&o++o@W. &@&  8@#o+&@W.  #@:    o@+
      :W@@WWWW@@8       +              :&W@@@@&    &W  .o#@@W&.   :W@WWW@@&
        +o&&&&+.                                                    +oooo.

                                                                     v3.22.2
                                           OWASP Amass Project - @owaspamass
                         In-depth Attack Surface Mapping and Asset Discovery


Usage: amass enum [options] -d DOMAIN

  -active
        Attempt zone transfers and certificate name grabs
  -addr value
        IPs and ranges (192.168.1.1-254) separated by commas
  -alts
        Enable generation of altered names
  -asn value
        ASNs separated by commas (can be used multiple times)
  -aw value
        Path to a different wordlist file for alterations
  -awm value
        "hashcat-style" wordlist masks for name alterations
  -bl value
        Blacklist of subdomain names that will not be investigated
  -blf string
        Path to a file providing blacklisted subdomains
  -brute
        Execute brute forcing after searches
  -cidr value
        CIDRs separated by commas (can be used multiple times)
  -config string
        Path to the INI configuration file. Additional details below
  -d value
        Domain names separated by commas (can be used multiple times)
  -demo
        Censor output to make it suitable for demonstrations
  -df value
        Path to a file providing root domain names
  -dir string
        Path to the directory containing the output files
  -dns-qps int
        Maximum number of DNS queries per second across all resolvers
  -ef string
        Path to a file providing data sources to exclude
  -exclude value
        Data source names separated by commas to be excluded
  -h    Show the program usage message
  -help
        Show the program usage message
  -if string
        Path to a file providing data sources to include
  -iface string
        Provide the network interface to send traffic through
  -include value
        Data source names separated by commas to be included
  -ip
        Show the IP addresses for discovered names
  -ipv4
        Show the IPv4 addresses for discovered names
  -ipv6
        Show the IPv6 addresses for discovered names
  -json string
        Path to the JSON output file
  -list
        Print the names of all available data sources
  -log string
        Path to the log file where errors will be written
  -max-depth int
        Maximum number of subdomain labels for brute forcing
  -max-dns-queries int
        Deprecated flag to be replaced by dns-qps in version 4.0
  -min-for-recursive int
        Subdomain labels seen before recursive brute forcing (Default: 1) (default 1)
  -nf value
        Path to a file providing already known subdomain names (from other tools/sources)
  -noalts
        Deprecated flag to be removed in version 4.0 (default true)
  -nocolor
        Disable colorized output
  -nolocaldb
        Deprecated feature to be removed in version 4.0
  -norecursive
        Turn off recursive brute forcing
  -o string
        Path to the text file containing terminal stdout/stderr
  -oA string
        Path prefix used for naming all output files
  -p value
        Ports separated by commas (default: 80, 443)
  -passive
        Disable DNS resolution of names and dependent features
  -r value
        IP addresses of untrusted DNS resolvers (can be used multiple times)
  -rf value
        Path to a file providing untrusted DNS resolvers
  -rqps int
        Maximum number of DNS queries per second for each untrusted resolver
  -scripts string
        Path to a directory containing ADS scripts
  -share
        Deprecated feature to be removed in version 4.0
  -silent
        Disable all output during execution
  -src
        Print data sources for the discovered names
  -timeout int
        Number of minutes to let enumeration run before quitting
  -tr value
        IP addresses of trusted DNS resolvers (can be used multiple times)
  -trf value
        Path to a file providing trusted DNS resolvers
  -trqps int
        Maximum number of DNS queries per second for each trusted resolver
  -v    Output status / debug / troubleshooting info
  -w value
        Path to a different wordlist file for brute forcing
  -wm value
        "hashcat-style" wordlist masks for DNS brute forcing
"""
from typing import Any, Dict, List
import subprocess
import tempfile
from websecmap.celery import app

from celery import group

from websecmap.app import log
from websecmap.organizations.models import Url
from websecmap.scanners import plannedscan
from websecmap.scanners.models import Activity
from websecmap.scanners.plannedscan import generic_retry_watcher
from websecmap.scanners.scanner.filter import filter_top_level_domains, generic_plan_scan
from websecmap.scanners.scanner.nuclei_http import convert_nuclei_data_to_json
from websecmap.scanners.support import kwargs_to_params

SCANNER_NAME = "subdomains_amass"


@app.task(queue="kickoff")
def plan_discover(**kwargs):
    generic_plan_scan(SCANNER_NAME, "discover", filter_top_level_domains, **kwargs)


@app.task(queue="kickoff")
def compose_planned_discover_task(**kwargs) -> group:
    urls = plannedscan.pickup(activity="discover", scanner=SCANNER_NAME, amount=kwargs.get("amount", 1))
    return compose_discover_task(urls)


def compose_manual_discover_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
):
    urls = filter_top_level_domains(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    return compose_discover_task(urls, **kwargs)


def compose_discover_task(urls, **kwargs) -> group:
    return group(
        discover.si(url.url, kwargs) | store.s(url.pk) | plannedscan.finish.si("discover", SCANNER_NAME, url.pk)
        for url in urls
    )


@app.task(queue="kickoff")
def retry_watcher():
    # Since only one scan can be run at one time, a reboot of the software might mean that a currently running
    # scan is terminated. The normal 'recovery' period is 48 hours, which is WAY too long. Instead of messing
    # with the existing recovery architecture, this function measures tasks that have been running for too long and
    # resets them to requested. At that moment the next scan can be picked up. Expecting a timeout of 30 minutes.
    # which should be way than more than enough to finish a scan on a domain.
    generic_retry_watcher(SCANNER_NAME, activity=Activity.discover, minutes=30)


# This task is run their own worker, because amass uses a lot of memory and is excruciatingly slow.
# Only one amass task can be run at the same time.
@app.task(queue="amass")
def discover(domain_name: str, scanner_keyword_arguments: Dict[str, Any] = None) -> List[str]:
    command = [
        "amass",
        # any param here is injected via the periodic task.
    ]

    if scanner_keyword_arguments:
        command += kwargs_to_params(scanner_keyword_arguments, prefix="-")
    else:
        # use some sane defaults to be able to perform a scan from the command line anyway, this gives the user
        # more power. This also makes the command testable from the command line.
        command += [
            "enum",
            "-nolocaldb",
            "-active",
            "-dns-qps",
            "1000",
            "-timeout",
            "10",
        ]

    command += [
        # always work with json lines
        "-json",
        # always write the same file to the tmp dir
        "tmpfile.json",
        "-d",
        domain_name,
    ]
    json_lines = call_amass(command)
    # reduce the amount of data we need to send between workers.
    return extract_urls_from_json(convert_nuclei_data_to_json(json_lines))


def call_amass(command: List[str]) -> str:
    # separated into a small function to be better testable
    with tempfile.TemporaryDirectory() as tmpdirname:
        log.debug("Running amass in temporary directory: %s", tmpdirname)
        log.debug("Running amass command: %s", " ".join(command))
        amass = subprocess.Popen(command, stdout=subprocess.PIPE, cwd=tmpdirname, stderr=subprocess.PIPE)
        amass.wait()
        data = amass.communicate()
        log.debug(data)

        with open(f"{tmpdirname}/tmpfile.json", "r") as f:
            json_lines = f.read()

    return json_lines


def extract_urls_from_json(json_data: List[Dict[str, Any]]) -> List[str]:
    # nogo: also extract the ip addresses and asn stuff, or not: just get that in the dedicated ip scanner.
    """
    {
      "name": "nl.dev.batch.internet.nl",
      "domain": "internet.nl",
      "addresses": [
        {
          "ip": "2a00:d00:ff:162:62:204:66:17",
          "cidr": "2a00:d00::/40",
          "asn": 41887,
          "desc": "PROLOCATION Transit policy pref 100"
        },
        {
          "ip": "62.204.66.17",
          "cidr": "62.204.64.0/22",
          "asn": 41887,
          "desc": "PROLOCATION Transit policy pref 100"
        }
      ],
      "tag": "crawl",
      "sources": [
        "CertSpotter",
        "RapidDNS",
        "Brute Forcing",
        "Crtsh",
        "NSEC Walk",
        "Active Crawl",
        "Active Cert",
        "AbuseIPDB"
      ]
    }
    """

    return [domain["name"] for domain in json_data]


@app.task(queue="storage")
def store(found_domains: List[str], store_to_model_id: Any) -> None:
    log.debug("Storing domains %s to organization %s", found_domains, store_to_model_id)

    url = Url.objects.filter(id=store_to_model_id).first()
    if not url:
        log.error("Could not store domains %s to url %s because no organization was found.", found_domains, url)
        return

    all_organizations_with_this_url = url.organization.all()
    if not all_organizations_with_this_url:
        # The scan could only have started with the url coupled to the organizaiton to begin with.
        # so this is a weird situation. Perhaps the 2nd level url got removed or so.
        log.error(
            "Could not store domains %s to organization with url %s because no organization was found.",
            found_domains,
            url,
        )
        return

    # now add this url to every organization that refers to it:
    for organization in all_organizations_with_this_url:
        for found_domain in found_domains:
            organization.add_url(found_domain)

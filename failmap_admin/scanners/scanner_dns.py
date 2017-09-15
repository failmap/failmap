# This is going to scan DNS using well known tools.

# DNS Recon:
# The Harvester: - going to deprecated

"""
DNS Recon in some cases things all subdomains are valid, correctly, because there is always an
answer. So we're going to test if a few random domains exist and such.

Afterwards, we do know that a subdomain exist, but we don't know what ports give results we can
audit. We will check for TLS on 443. There are infinite possibilities.
We can check both for endpoints on http and https for the new domains. So they can be picked up by
other scanners.
"""
import subprocess

from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.scanner_http import ScannerHttp


class ScannerDns:

    harvester_path = "/var/www/faalkaart/test/theHarvester/theHarvester.py"

    # todo: make a "tool" dir, or something so the harvester and such are always available.
    # todo: if ScannerHttp.has_internet_connection():
    def manual_harvesting(self, url):
        subdomains = ScannerDns.subdomains_harvester(url)

        for subdomain in subdomains:
            fulldomain = subdomain + "." + url
            if ScannerHttp.resolves(fulldomain):
                if not Url.objects.all().filter(url=fulldomain).exists():
                    print("Added domain to database: %s" % fulldomain)
                    o = Organization.objects.get(url__url=url)
                    u = Url()
                    u.organization = o
                    u.url = fulldomain
                    u.save()
                else:
                    print("Subdomain already in the database: %s" % fulldomain)
            else:
                print("Subdomain did not resolve: %s" % fulldomain)

    @staticmethod
    def subdomains_harvester(url):
        # todo: very ugly parsing, should be just reading the XML output.
        # python theHarvester.py -d zutphen.nl -b google -l 100
        engine = "google"
        process = subprocess.Popen(['python', ScannerDns.harvester_path,
                                    '-d', url,
                                    '-b', engine,
                                    '-s', '0',
                                    '-l', '100'], stdout=subprocess.PIPE)

        output = str(process.stdout.read())
        # we only care about the stuff after "[-] Resolving hostnames IPs... "
        hostnames = output[output.find("[-] Resolving hostnames IPs... ") + 32:len(output)]
        hostname_list = hostnames.split("\\n")
        subdomains = []
        for hostname in hostname_list:
            # print("Found hostname: %s" % hostname)
            if "." + url in hostname:
                subdomain_with_ip = hostname[0:hostname.find("." + url)]
                subdomain = subdomain_with_ip[subdomain_with_ip.find(':')+1:len(subdomain_with_ip)]
                subdomains.append(subdomain)
                print("Found subdomain %s" % subdomain)

        return subdomains

    def make_wordlist(self):
        # todo: per branche wordlists, more to the point
        prefixes = []
        urls = Url.objects.all()
        for url in urls:
            positions = [pos for pos, char in enumerate(url.url) if char == '.']
            if len(positions) > 1:
                prefixes.append(url.url[0:positions[len(positions)-2]])
        # print(set(prefixes))
        return set(prefixes)

    def dnsrecon(self, url):
        # requires: netaddr, dnspython
        # Dictionaries of the local language are available on wiktionary.
        # https://nl.wiktionary.org/wiki/WikiWoordenboek:OpenTaal
        # https://www.opentaal.org/

        # Brute force op DNS:
        # python dnsrecon.py --domain amsterdam.nl -t brt -D ./OpenTaal-210G-woordenlijsten/
        # OpenTaal-210G-basis-gekeurd.txt -c output_brt.csv
        # takes about 5 minutes

        # google search, zone transfers en alles included:
        # python dnsrecon.py --domain amsterdam.nl -D ./OpenTaal-210G-woordenlijsten/
        # OpenTaal-210G-basis-gekeurd.txt -c output.csv
        # brute force takes a few hours. You don't have to do this a lot fortunately.

        # works with json output, which is easy to parse. Also supports a google seach, so probably
        # ditch theharvester.
        return

    def import_dnsrecon_report(self, json):

        return

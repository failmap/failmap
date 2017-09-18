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


# todo: record that some domains have a catch all, and should not be scanned.
# the catch all is sometimes not detected by dnsrecon
class ScannerDns:

    working_directory = "/var/www/faalkaart/test/dnsrecon/output/"

    harvester_path = "/var/www/faalkaart/test/theHarvester/theHarvester.py"
    dnsrecon_path = "/var/www/faalkaart/test/dnsrecon/dnsrecon.py"

    wordlist_dutch = "/var/www/faalkaart/test/dnsrecon/wordlists/OpenTaal-210G-basis-gekeurd.txt"
    wordlist_3letters = "/var/www/faalkaart/test/dnsrecon/wordlists/threeletterwordlist.txt"
    wordlist_knownsudomains = "/var/www/faalkaart/test/dnsrecon/wordlists/knownsubdomains.txt"

    # todo: make a "tool" dir, or something so the harvester and such are always available.
    # todo: if ScannerHttp.has_internet_connection():
    def manual_harvesting(self, url):
        subdomains = ScannerDns.subdomains_harvester(url)

        for subdomain in subdomains:
            ScannerDns.add_subdomain(subdomain, url)

    @staticmethod
    # todo: move this to url logic / url manager.
    def add_subdomain(subdomain, url):
        fulldomain = subdomain + "." + url.url
        print("Trying to add subdomain to database: %s" % fulldomain)
        if ScannerHttp.resolves(fulldomain):
            if not Url.objects.all().filter(url=fulldomain, organization=url.organization).exists():
                print("*** Added domain to database: %s" % fulldomain)
                # naive adding, since we don't have an organization.
                u = Url()
                u.organization = url.organization
                u.url = fulldomain
                u.save()
                return u
            else:
                print("Subdomain already in the database: %s" % fulldomain)
        else:
            print("Subdomain did not resolve: %s" % fulldomain)
        return

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

    @staticmethod
    def update_wordlist_known_subdomains():
        # todo: per branche wordlists, more to the point
        prefixes = []
        urls = Url.objects.all()
        for url in urls:
            positions = [pos for pos, char in enumerate(url.url) if char == '.']
            if len(positions) > 1:
                prefixes.append(url.url[0:positions[len(positions)-2]])
        # print(set(prefixes))
        unique_prefixes = set(prefixes)

        with open(ScannerDns.wordlist_knownsudomains, "w") as text_file:
            for unique_prefix in unique_prefixes:
                text_file.write(unique_prefix + '\n')

        return unique_prefixes

    def make_threeletterwordlist(self):
        import itertools
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

    # 180.000 words
    def organization_brute_dutch(self, organization):
        urls = ScannerDns.topleveldomains(organization)
        wordlist = ScannerDns.wordlist_dutch
        return ScannerDns.dnsrecon_brute(urls, wordlist)

    # 18278 words
    # organizations _LOVE_ three # letter acronyms!
    def organization_brute_threeletters(self, organization):
        urls = ScannerDns.topleveldomains(organization)
        wordlist = ScannerDns.wordlist_3letters
        return ScannerDns.dnsrecon_brute(urls, wordlist)

    # hundreds of words
    # todo: language matters, many of the NL subdomains don't make sense in other countries.
    def organization_brute_knownsubdomains(self, organization):
        ScannerDns.update_wordlist_known_subdomains()
        urls = ScannerDns.topleveldomains(organization)
        wordlist = ScannerDns.wordlist_knownsudomains
        return ScannerDns.dnsrecon_brute(urls, wordlist)

    @staticmethod
    def dnsrecon_brute(urls, wordlist):
        for url in urls:
            print("Checking DNS of toplevel domain: %s" % url.url)
            print("Using wordlist: %s" % wordlist)
            file = "%s_data_brute.json" % url.url
            path = ScannerDns.working_directory + file

            print("DNS results will be stored in file: %s" % path)

            # never continue with wildcard domains
            p = subprocess.Popen(['python', ScannerDns.dnsrecon_path,
                                  '--domain', url.url,
                                  '-t', 'brt',
                                  '-D', wordlist,
                                  '-j', path], stdin=subprocess.PIPE)
            p.stdin.write('n'.encode(encoding='utf-8'))  # never brute a wildcard
            p.communicate()

            return ScannerDns.import_dnsrecon_report(url, path)

    # todo: move to Organization manager
    @staticmethod
    def topleveldomains(organization):
        return Url.objects.all().filter(organization=organization, url__iregex="^[^.]*\.[^.]*$")

    def dnsrecon_google(self, url):
        # todo: make this new manual scan.
        # requires: netaddr, dnspython
        # Dictionaries of the local language are available on wiktionary.
        # https://nl.wiktionary.org/wiki/WikiWoordenboek:OpenTaal
        # https://www.opentaal.org/

        # Brute force op DNS:
        # python dnsrecon.py --domain amsterdam.nl -j output_brt.json
        return

    @staticmethod
    # todo: also perform basic endpoint scans for new subdomains
    def import_dnsrecon_report(url, path):
        # note: the order of the records in the report matters(!)

        import json
        with open(path) as data_file:
            data = json.load(data_file)
            addedlist = []
            for record in data:
                if "arguments" in record.keys():
                    continue

                if record["name"].endswith(url.url):
                    subdomain = record["name"][0:len(record["name"])-len(url.url)-1]
                    # print(subdomain.lower())
                    added = ScannerDns.add_subdomain(subdomain.lower(), url)
                    if added:
                        addedlist.append(added)
        return addedlist

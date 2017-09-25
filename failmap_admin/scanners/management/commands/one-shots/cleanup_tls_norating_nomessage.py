import ipaddress
import logging

import tldextract
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Organization
from failmap_admin.scanners.models import Endpoint, TlsQualysScan, Url, TlsQualysScratchpad

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Cleans up TLS scans that have a 0 rating and no message. Usually that would be a' \
           'unable to resolve domain or something like that. We correlate to unresolvable domains.'

    """
    You probably don't need to run this anymore...
    
    Non resolvable, alsways 0 scans are just nonsense: the domain just doesn't exist and it creates
    false scores.
    """

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/

    def handle(self, *args, **options):

        Command.figure_out_zero_reason()
        # non_presented_scans = TlsQualysScan.objects.all().filter(qualys_message__isnull=True,
        #                                                         qualys_rating="0")
#
        # for scan in non_presented_scans:
        #     print(scan, scan.endpoint)
        # return
#
#

    # todo: read out certhostnames to find more domains :)
    # https://stackoverflow.com/questions/6578986/how-to-convert-json-data-into-a-python-object
    @staticmethod
    def figure_out_zero_reason():
        urls = Url.objects.all().filter()
        i = 0
        for url in urls:
            nonsense_scans = TlsQualysScan.objects.all().filter(endpoint__url=url,
                                                                qualys_message__isnull=True,
                                                                qualys_rating="0")

            # print("Scans to place: %s" % nonsense_scans.count())

            for scan in nonsense_scans:

                print("Message: %s" % scan.qualys_message)

                # get the latest scratch:
                try:
                    scratch = TlsQualysScratchpad.objects.all().filter(domain=url.url,
                                                                       when__lte=scan.scan_moment).latest("when")

                    # read status
                    import json
                    json = json.loads(scratch.data)
                    print("Endpoint: %s, Scan: %s" % (scan, scan.endpoint))
                    print("Message from %s: %s" % (scratch.when, json["endpoints"][0]["statusMessage"]))
                    print(json["endpoints"][0]["statusMessage"])

                    # ready, probably for another endpoint. Or for something else... # there a six
                    if json["endpoints"][0]["statusMessage"] != "Ready":
                        scan.qualys_message = json["endpoints"][0]["statusMessage"]
                        # scan.save()
                except ObjectDoesNotExist:
                    print("Could not find scan... ")
                    # just copy the most recent message back to the past. We assume the rating
                    # has always been the same in the past.

                    try:
                        oldest_rating_with_message = TlsQualysScan.objects.all().filter(
                            endpoint__url=url,
                            qualys_message__isnull=False,
                            qualys_rating="0").earliest("rating_determined_on")

                        print("The oldest known rating had message: %s" % oldest_rating_with_message.qualys_message)
                        print("Endpoint: %s, Scan: %s" % (scan, scan.endpoint))
                        print(scan.rating_determined_on)
                        i = i + 1
                        scan.qualys_message = oldest_rating_with_message.qualys_message
                        # scan.save()


                    except ObjectDoesNotExist:
                        print("Scan never had an early message as well. Now what?")
                        print("Endpoint: %s, Scan: %s" % (scan, scan.endpoint))
                        i = i + 1
                        # Just re-scan the url some time in the future, and then deal with it
                        # the modern way.
                        scan.delete()


        print("There are %s zero rating without message." % i)




    @staticmethod
    # can't figure out why this happened: polutes database, clean it.
    def delete_all_with_zero_and_no_message():
        urls = Url.objects.all().filter()
        for url in urls:
            nonsense_scans = TlsQualysScan.objects.all().filter(endpoint__url=url,
                                                                qualys_message__isnull=True,
                                                                qualys_rating="0")

            for scan in nonsense_scans:
                print(scan, scan.endpoint)
                # scan.delete()


    @staticmethod
    def clean_always_zero_scans():
        """
        These urls always had a 0 returned, and no message: even with multiple scans: meaning the
        scan was not worth it. In the beginning of this project we saved scans that had a 0 rating
        without a message: you would not know if the certificate was invalid for the domain, or that
        there was no connection to the server.
        :return:
        """
        urls = Url.objects.all().filter()  # if resolvable: cert wrong for domain
                                                                # name?

        for url in urls:
            # all normal scans
            scans = TlsQualysScan.objects.all().filter(endpoint__url=url)

            # scans that have 0 points, no message (like cert wrong for domain name)
            nonsense_scans = TlsQualysScan.objects.all().filter(endpoint__url=url,
                                                                qualys_message__isnull=True,
                                                                qualys_rating="0")

            if scans.count() == nonsense_scans.count() and scans.count() > 0:
                logger.debug(url)
                logger.debug(
                    "Scans on this url: %s, nonsense: %s" % (scans.count(), nonsense_scans.count()))
                logger.debug("Scans eligable for deletion.")

                for scan in nonsense_scans:
                    # scan.delete()
                    print("Not deleting... uncomment for deletion.")
                    print(scan, scan.qualys_message)

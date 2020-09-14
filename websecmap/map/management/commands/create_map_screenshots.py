import logging
import platform
import subprocess

from constance import config
from django.conf import settings
from django.core.management.base import BaseCommand

from websecmap.map.models import Configuration

log = logging.getLogger(__package__)

firefox = settings.TOOLS["firefox"]["executable"][platform.system()]
chrome = settings.TOOLS["chrome"]["executable"][platform.system()]


# Make sure you have a profile named 'screenshots', run firefox once with firefox -P to create such a profile.
# a profile is a clean firefox, with a separate set of extensions etc.

# if you're getting shell after starting firefox, there was probably a crash or something else. Open firefox using
# firefox -P screenshots to clean the instance.


class Command(BaseCommand):
    help = "Creates a series of screenshots showing just the map, countries and filters."

    def handle(self, *args, **options):

        filters = [
            "",
            "ftp",
            "DNSSEC",
            "http_security_header_x_xss_protection",
            "http_security_header_x_content_type_options",
            "http_security_header_x_frame_options",
            "tls_qualys_certificate_trusted",
            "tls_qualys_encryption_quality",
            "http_security_header_strict_transport_security",
            "plain_https",
        ]

        moments_in_time = range(0, 500, 7)

        map_configurations = Configuration.objects.all()

        for configuration in map_configurations:
            for moment_in_time in moments_in_time:
                for filter in filters:
                    log.debug(
                        "%s %s %s %s"
                        % (configuration.country, configuration.organization_type.name, filter, moment_in_time)
                    )

                    map_only_url = config.PROJECT_WEBSITE + "/map_only/%s/%s/%s/%s/" % (
                        configuration.country,
                        configuration.organization_type.name,
                        moment_in_time,
                        filter,
                    )

                    filename = settings.TOOLS["firefox"]["screenshot_output_dir"] + "%s_%s_%s_%s.png" % (
                        configuration.country,
                        configuration.organization_type.name,
                        filter,
                        moment_in_time,
                    )

                    screenshot_chrome(map_only_url, filename)


# https://bugzilla.mozilla.org/show_bug.cgi?id=1518116
# one year and still cannot use it to make screenshots, they don't test this it seems.
def screenshot_firefox(url, filename):
    command = [
        firefox,
        "-headless",
        "-screenshot",
        filename,
        url,
        "--window-size=1920,1080",
        "-P",
        "screenshots",
        "-no-remote",
    ]
    log.debug("Called command: %s" % " ".join(command))
    subprocess.call(command)


def screenshot_chrome(url, filename):
    command = [
        chrome,
        "--disable-gpu",
        "--headless",
        "--screenshot=%s" % filename,
        "--window-size=1600,1200",
        "--virtual-time-budget=5000",
        url,
    ]
    log.debug("Called command: %s" % " ".join(command))
    subprocess.call(command)

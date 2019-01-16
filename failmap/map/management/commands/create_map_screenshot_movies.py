import logging
import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand
from moviepy.editor import ImageClip, concatenate_videoclips

from failmap.map.models import Configuration

log = logging.getLogger(__package__)


def tryint(s):
    try:
        return int(s)
    except BaseException:
        return s


def alphanum_key(s):
    """ Turn a string into a list of string and number chunks.
        "z23a" -> ["z", 23, "a"]
    """
    return [tryint(c) for c in re.split('([0-9]+)', s)]


class Command(BaseCommand):
    help = """Uses moviepy to create a few movies based on screenshots."""

    def handle(self, *args, **options):

        # no empty, because that loads all screenshots
        filters = ['all', "ftp", "DNSSEC", "http_security_header_x_xss_protection",
                   "http_security_header_x_content_type_options", "http_security_header_x_frame_options",
                   "tls_qualys_certificate_trusted", "tls_qualys_encryption_quality",
                   "http_security_header_strict_transport_security", "plain_https"]

        map_configurations = Configuration.objects.all()

        for configuration in map_configurations:
            for filter in filters:
                create_movie(filter, configuration)


def create_movie(filter, configuration):
    file_filter = "%s_%s_%s" % (configuration.country, configuration.organization_type.name, filter)

    log.info("Creating movie for %s" % file_filter)

    log.debug('Loading filenames')
    files = [filename for filename in os.listdir(
        settings.TOOLS['firefox']['screenshot_output_dir']) if filename.startswith(file_filter)]

    # some filters may not result in any files
    if not files:
        log.debug('No suitable images could be found for this Configuration / filter. Did you make screenshots?')
        return

    files.sort(key=alphanum_key)
    files = reversed(files)
    log.debug('Creating clips')
    clips = [ImageClip(settings.TOOLS['firefox']['screenshot_output_dir'] + file).set_duration(0.2) for file in files]
    log.debug('Writing file')
    concat_clip = concatenate_videoclips(clips, method="compose")
    concat_clip.write_videofile("%svideo_%s.mp4" % (
        settings.TOOLS['firefox']['screenshot_output_dir'], file_filter), fps=30)

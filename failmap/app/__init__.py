import logging
from collections import defaultdict

from django.conf import settings

log = logging.getLogger(__name__)

# log database settings during init for debug purposes
log.info('Database settings: {ENGINE}, {NAME}, {USER}, {HOST}'.format_map(
    defaultdict(str, **settings.DATABASES['default'])))

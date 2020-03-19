# Note: run make fix and make check before committing code.

import logging

from constance import config

from websecmap.api.logic import organization_and_url_import

log = logging.getLogger(__package__)

# added to not have pyflakes complaining about the unused import.
_all_ = organization_and_url_import

log.debug(config.ZORGKAART_FILTER)

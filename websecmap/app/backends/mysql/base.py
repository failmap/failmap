"""Wraps Django MySQL backend in connection retry logic.

Because of the asynchronous nature of environments we might deploy in (docker-composer) the
database connection might not always be available when the failmap app is started. We take some
effort to retry connecting to the database before giving up.
"""

import logging
import os

import django
from retry import retry

TRIES = os.environ.get("DB_CONNECT_RETRIES", 10)

log = logging.getLogger(__name__)

try:
    from django.db.backends.mysql.base import DatabaseWrapper as MysqlDatabaseWrapper
except django.core.exceptions.ImproperlyConfigured:
    log.info("mysqlclient library not installed, skipping mysql specific code")
else:

    class DatabaseWrapper(MysqlDatabaseWrapper):
        # retry
        @retry(logger=log, tries=TRIES, delay=1, backoff=2, max_delay=5)
        def get_new_connection(self, *args, **kwargs):
            connection = super().get_new_connection(*args, **kwargs)
            return connection

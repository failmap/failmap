""" A number of functions that help inspecting database queries when other methods fail. """

import logging

log = logging.getLogger(__package__)


def count_queries(message: str = ""):
    """
    Helps figuring out if django is silently adding more queries / slows things down. Happens when you're
    asking for a property that was not in the original query.

    Note, this stops counting at 9000. See BaseDatabaseWrapper.queries_limit

    :return:
    """
    from django.db import connection
    queries_performed = len(connection.queries)
    if queries_performed > 9000:
        log.debug("Maximum number of queries reached.")

    length_short, length_medium, length_long = 0, 0, 0

    for query in connection.queries:
        if len(query['sql']) <= 100:
            length_short += 1
        if 100 < len(query['sql']) < 300:
            length_medium += 1
        if len(query['sql']) >= 300:
            length_long += 1

    log.debug("# queries: %3s L: %2s, M %2s, S:%2s(%s)" %
              (len(connection.queries), length_long, length_medium, length_short, message))


def show_last_query():
    from django.db import connection

    if not len(connection.queries):
        return

    log.debug(connection.queries[len(connection.queries) - 1])


def show_queries():
    from django.db import connection
    log.debug(connection.queries)


def query_contains_begin():
    """
    A large number of empty begin queries was issues on sqlite during development. This was just as much as the normal
    inserts and saves, which is 60.000 roundtrips. Staring with BEGIN but never finishing the transaction makes no
    sense. WHY? When are the transactions stopped?

    It's embedded in Django's save and delete functions. It always issues a BEGIN statement, even if it's not needed.

    This is the reason:
    https://github.com/django/django/blob/f1d163449396f8bab6c50f4b8b54829d139feda2/django/db/backends/sqlite3/base.py

    From the code:
    Start a transaction explicitly in autocommit mode.
    Staying in autocommit mode works around a bug of sqlite3 that breaks savepoints when autocommit is disabled.

    And more meaningful comments here:
    https://github.com/django/django/blob/717ee63e5615a6c3a018351a07028513f9b01f0b/django/db/backends/base/base.py

    OK, we're rolling with it. Thnx open source docs and django devs for being clear.
    :return:
    """
    from django.db import connection

    for query in connection.queries:
        if query['sql'] == 'BEGIN':
            log.error('BEGIN')

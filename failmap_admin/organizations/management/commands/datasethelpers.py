import logging

from django.db import connection

from failmap_admin import settings

logger = logging.getLogger(__package__)


def sqlite_has_correct_referential_integrity():
    # http://www.sqlite.org/pragma.html#pragma_foreign_key_check
    logger.info(
        'Checking for foreign key issues, and generating possible SQL to remediate issues.')

    cursor = connection.cursor()
    cursor.execute('''PRAGMA foreign_key_check;''')
    rows = cursor.fetchall()
    if rows:
        logger.error("Cannot create export. There are incomplete foreign keys. "
                     "See information above to fix this. "
                     "Please fix these issues manually and try again.")

    for row in rows:
        logger.info("%25s %6s %25s %6s" % (row[0], row[1], row[2], row[3]))

    if rows:
        logger.error(
            "Here are some extremely crude SQL statements that might help fix the problem.")
    for row in rows:
        logger.info("DELETE FROM %s WHERE id = \"%s\";" % (row[0], row[1]))

    if rows:
        return False
    return True


def check_referential_integrity():
    # this only works for ssqlite.
    if "sqlite" in settings.DATABASES["default"]["ENGINE"]:
        if not sqlite_has_correct_referential_integrity():
            logger.error("Fix above issues. Not proceeding.")
            return
    else:
        logger.error("This export might have incorrect integrity: no foreign key check for "
                     "this engine was implemented. Loaddata might not accept this import. "
                     "Perform a key check manually and then alter this code to continue.")
        return

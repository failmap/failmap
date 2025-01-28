import gzip
import logging
from gzip import BadGzipFile

from django.db import models
from jsonfield.fields import JSONFieldMixin

log = logging.getLogger(__name__)


class CompressedJSONField(JSONFieldMixin, models.BinaryField):
    """
    This is exactly the same as a JSONField, except that the storage is compressed transparently with gzip.
    This saves a lot of space while the app stays functioning the way it does.

    GZIP might not have the best compression ratio, but the compression speed and decompression time are the best.
    The advice in the article (gzip -6 or xz -1) makes sense for this type of data.

    Compression level 4 is chosen as that's twice as fast while only losing about a percent of compression ratio.
    Some CPU speed is important and shaving off 90 or 89% at twice the CPU cost matters.

    Todo: the column needs to be bytes. How does that work in django database? -> seems to work instantly already.
    But perhaps not in postgres of mariadb. We'll see what happens during tests.

    https://www.rootusers.com/gzip-vs-bzip2-vs-xz-performance-comparison/

    Also tested by hand in the admin interface.
    """

    def to_python(self, value):
        # there is a difference between "" and None, let's reduce all to None.
        if not value:
            return super().to_python(value)

        try:
            # when migrating the data may not be compressed, so fallback to returning the data as json
            data = gzip.decompress(value)
        except (BadGzipFile, TypeError) as e:
            log.error("Unable to decompress data, using original: %s", e)
            if isinstance(value, memoryview):
                # postgresql
                data = bytes(value).decode("utf8")
            # memoryview is bytes, so an if statement would always be correct
            elif isinstance(value, bytes):
                # mysql
                data = value.decode("utf8")
            else:
                data = value
        return super().to_python(data)

    def from_db_value(self, value, expression, connection):
        if not value:
            return super().from_db_value(value, expression, connection)

        try:
            # when migrating the data may not be compressed, so fallback to returning the data as json
            data = gzip.decompress(value)
        except (BadGzipFile, TypeError) as e:
            log.error("Unable to decompress data, using original: %s", e)
            if isinstance(value, memoryview):
                # postgresql
                data = bytes(value).decode("utf8")
            elif isinstance(value, bytes):
                # mysql
                data = value.decode("utf8")
            else:
                data = value
        return super().from_db_value(data, expression, connection)

    def get_prep_value(self, value):
        string = super().get_prep_value(value)

        # fix TypeError: encoding without a string argument, gzip cannot deal with None, only with byte strings
        if string is None:
            return None

        return gzip.compress(bytes(string, "UTF-8"), compresslevel=4)

    # disabled useless-super-delegation due to not knowing what super class is called exactly. This code
    # might be just be removed and it could work fine, but no test for that is written yet. So no confidence in removing
    def value_to_string(self, obj):  # pylint: disable=useless-super-delegation
        # https://docs.djangoproject.com/en/5.0/ref/models/fields/#django.db.models.Field.value_to_string
        # normaly serialization would work, but in this case it's just a json object.
        return super().value_to_string(obj)
